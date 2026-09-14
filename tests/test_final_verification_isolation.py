import unittest

from core.research.comparison_state import (
    ComparisonState,
    VerificationStatus,
)
from core.research.evidence import ObservationStore
from core.research.research_tools import create_research_tools

from tests.test_product_acceptance import PAGE, SELECTION, URL
from tests.test_research_workflow import ResearchFixture, SCOPES


class FinalVerificationIsolationTests(unittest.TestCase):
    """Regression tests for final-page verification isolation."""

    def test_bad_final_quote_does_not_destroy_verified_winner_in_every_category(self):
        """
        A bad ref/quote selection during the final freshness check is not evidence
        that the already-verified offer became invalid. Keep the durable verified
        winner intact and only leave final-page confirmation unresolved.
        """
        for category in SCOPES:
            with self.subTest(category=category):
                fixture = ResearchFixture(category)

                self.assertIn("VERIFIED RESULT", fixture.verify())
                self.assertIn("APPROVED", fixture.finalize())

                before_total = fixture.result.public_total
                before_observation = fixture.result.verification_observation_id
                before_history = list(fixture.result.price_history)

                payload = fixture.capture()
                payload["quote"]["identity_evidence"] = (
                    "THIS TEXT DOES NOT EXIST IN THE SELECTED OFFER SUBTREE"
                )

                response = fixture.tools["research_confirm_final_page"].invoke(payload)

                self.assertIn("FINAL PAGE BLOCKED", response)

                self.assertTrue(
                    fixture.result.verified,
                    "A final-check evidence-selection failure must not clear the prior verification.",
                )
                self.assertEqual(
                    fixture.result.verification_status,
                    VerificationStatus.VERIFIED,
                )
                self.assertEqual(
                    fixture.state.finalized_result_id,
                    fixture.result.result_id,
                    "A bad final-check payload must not un-finalize a still-verified winner.",
                )
                self.assertEqual(fixture.result.public_total, before_total)
                self.assertEqual(
                    fixture.result.verification_observation_id,
                    before_observation,
                    "Failed final evidence must not replace the last good verification evidence.",
                )
                self.assertEqual(
                    fixture.result.price_history,
                    before_history,
                    "Failed final evidence must not append or rewrite verified price history.",
                )
                self.assertFalse(fixture.state.final_page_verified)

                # A corrected fresh snapshot must still be able to confirm the page.
                corrected = fixture.tools["research_confirm_final_page"].invoke(
                    fixture.capture()
                )
                self.assertIn("FINAL PAGE CONFIRMED", corrected)
                self.assertTrue(fixture.result.verified)
                self.assertTrue(fixture.state.is_finalized())
                self.assertTrue(fixture.state.final_page_verified)

    def test_final_page_retry_exhaustion_does_not_block_the_offer(self):
        """
        Final-page evidence selection also needs a finite retry budget, but that
        budget belongs to final confirmation, not to candidate verification.
        Exhaustion may block final-page confirmation; it must not turn the winner
        itself into a BLOCKED candidate.
        """
        fixture = ResearchFixture("hotel")

        self.assertIn("VERIFIED RESULT", fixture.verify())
        self.assertIn("APPROVED", fixture.finalize())

        for _ in range(6):
            payload = fixture.capture()
            payload["quote"]["identity_evidence"] = (
                "THIS TEXT DOES NOT EXIST IN THE SELECTED OFFER SUBTREE"
            )
            response = fixture.tools["research_confirm_final_page"].invoke(payload)
            if getattr(fixture.state, "final_page_blocked", False):
                break

        self.assertTrue(
            getattr(fixture.state, "final_page_blocked", False),
            "Final confirmation must have its own bounded terminal failure state.",
        )
        self.assertTrue(fixture.result.verified)
        self.assertEqual(
            fixture.result.verification_status,
            VerificationStatus.VERIFIED,
        )
        self.assertTrue(
            fixture.state.is_finalized(),
            "The previously verified winner must survive final confirmation exhaustion.",
        )
        self.assertFalse(fixture.state.final_page_verified)
        self.assertTrue(
            fixture.state.is_ready_to_return(),
            "After bounded final-confirmation failure, research should be able to report "
            "the verified winner while clearly saying the final page was not confirmed.",
        )
        self.assertIn(
            "RETRY BUDGET EXHAUSTED",
            response,
        )

    def test_product_ref_error_during_final_check_uses_final_page_budget_only(self):
        """
        Product ref selection can fail before the generic final-page validator.
        Those failures must still be isolated from the durable product verification.
        """
        state = ComparisonState(
            query="Logitech Superlight 2 mouse en ucuz fiyatını araştır",
            category="product",
            target_product="Logitech Superlight 2",
            criteria={"quantity": 1},
            planned_sources=["Google Shopping"],
        )
        store = ObservationStore()
        tools = {
            tool.name: tool
            for tool in create_research_tools(lambda: state, store)
        }

        tools["research_start_source"].invoke({"source": "Google Shopping"})
        discovery = store.capture(
            "https://www.google.com/search?tbm=shop&q=Logitech+Superlight+2",
            "Logitech Superlight 2 listing",
        )
        tools["research_record_discovery_attempt"].invoke(
            {
                "source": "Google Shopping",
                "query": "Logitech Superlight 2",
                "observation_id": discovery.observation_id,
            }
        )
        added = tools["research_add_result"].invoke(
            {
                "title": "Logitech Superlight 2",
                "source": "Google Shopping",
                "price": 4500,
                "currency": "TRY",
                "url": discovery.page_url,
                "offer_url": URL,
                "observation_id": discovery.observation_id,
            }
        )
        self.assertIn("STORED RESULT:", added)

        result = state.results[0]

        first_snapshot = store.capture(URL, PAGE)
        verified = tools["research_verify_product"].invoke(
            {
                "result_id": result.result_id,
                "observation_id": first_snapshot.observation_id,
                "selection": SELECTION,
                "final_check": False,
            }
        )
        self.assertIn("VERIFIED RESULT:", verified)

        tools["research_complete_source"].invoke(
            {
                "source": "Google Shopping",
                "outcome": "completed",
                "coverage_summary": "Verified product offer.",
            }
        )
        self.assertIn(
            "FINALIZATION APPROVED",
            tools["research_finalize"].invoke({"result_id": result.result_id}),
        )

        before_observation = result.verification_observation_id
        before_total = result.public_total

        bad_selection = {
            **SELECTION,
            "offer_ref": "f12e142",
        }
        final_snapshot = store.capture(URL, PAGE)
        response = tools["research_verify_product"].invoke(
            {
                "result_id": result.result_id,
                "observation_id": final_snapshot.observation_id,
                "selection": bad_selection,
                "final_check": True,
            }
        )

        self.assertIn("FINAL PAGE BLOCKED", response)
        self.assertTrue(result.verified)
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(state.finalized_result_id, result.result_id)
        self.assertEqual(result.verification_observation_id, before_observation)
        self.assertEqual(result.public_total, before_total)

        # Correct refs on a new snapshot must still confirm the final page.
        corrected_snapshot = store.capture(URL, PAGE)
        corrected = tools["research_verify_product"].invoke(
            {
                "result_id": result.result_id,
                "observation_id": corrected_snapshot.observation_id,
                "selection": SELECTION,
                "final_check": True,
            }
        )
        self.assertIn("FINAL PAGE CONFIRMED", corrected)
        self.assertTrue(state.final_page_verified)


if __name__ == "__main__":
    unittest.main()
