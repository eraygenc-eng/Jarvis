import unittest

from core.research.comparison_state import (
    ComparisonState,
    VerificationStatus,
)
from core.research.evidence import ObservationStore
from core.research.ranking import get_pending_verifications
from core.research.research_manager import product_criteria
from core.research.research_tools import create_research_tools
from core.research.source_planner import plan_sources

from tests.test_product_acceptance import PAGE, SELECTION, URL
from tests.test_research_workflow import ResearchFixture, SCOPES


class VerificationRetryGuardTests(unittest.TestCase):
    """Regression tests for the verification retry loop seen in live research."""

    @staticmethod
    def _bad_generic_payload(fixture: ResearchFixture):
        payload = fixture.capture()
        payload["quote"]["identity_evidence"] = (
            "THIS TEXT DOES NOT EXIST IN THE SELECTED OFFER SUBTREE"
        )
        return payload

    def test_repeated_generic_verification_failure_becomes_terminal_in_every_category(self):
        """
        The shared verification lifecycle must be bounded for products, flights,
        hotels and car rentals. One failure may be retried, but repeated failures
        must eventually make the candidate terminal instead of leaving it PENDING
        forever.
        """
        for category in SCOPES:
            with self.subTest(category=category):
                fixture = ResearchFixture(category)

                first = fixture.tools["research_verify_result"].invoke(
                    self._bad_generic_payload(fixture)
                )

                self.assertIn("VERIFICATION BLOCKED", first)
                self.assertEqual(
                    fixture.result.verification_status,
                    VerificationStatus.PENDING,
                    "A single correctable evidence failure should still allow a retry.",
                )

                # The exact numeric policy is intentionally not hard-coded here.
                # The implementation only has to guarantee a small finite bound.
                for _ in range(4):
                    fixture.tools["research_verify_result"].invoke(
                        self._bad_generic_payload(fixture)
                    )
                    if (
                        fixture.result.verification_status
                        == VerificationStatus.BLOCKED
                    ):
                        break

                self.assertEqual(
                    fixture.result.verification_status,
                    VerificationStatus.BLOCKED,
                    "Repeated verification failures must become terminal within five attempts.",
                )

                self.assertNotIn(
                    fixture.result,
                    get_pending_verifications(fixture.state),
                    "A terminal candidate must disappear from the pending-verification queue.",
                )

                response = fixture.tools["research_verify_result"].invoke(
                    fixture.capture()
                )

                self.assertIn(
                    "VERIFICATION SKIPPED",
                    response,
                    "A terminal candidate must not be verified again.",
                )
                self.assertEqual(
                    fixture.result.verification_status,
                    VerificationStatus.BLOCKED,
                )

    def test_terminal_failed_candidate_no_longer_blocks_source_completion(self):
        """
        Once retry exhaustion makes a candidate terminal, source research must
        be able to finish and move on instead of bouncing back to verification.
        """
        fixture = ResearchFixture("hotel")
        fixture.state.start_source("Discovery")

        for _ in range(5):
            fixture.tools["research_verify_result"].invoke(
                self._bad_generic_payload(fixture)
            )
            if (
                fixture.result.verification_status
                == VerificationStatus.BLOCKED
            ):
                break

        self.assertEqual(
            fixture.result.verification_status,
            VerificationStatus.BLOCKED,
        )

        discovery = fixture.store.capture(
            "https://discovery.example/search",
            "Hotel search results inspected",
        )
        fixture.tools["research_record_discovery_attempt"].invoke(
            {
                "source": "Discovery",
                "query": "hotel search",
                "observation_id": discovery.observation_id,
            }
        )

        response = fixture.tools["research_complete_source"].invoke(
            {
                "source": "Discovery",
                "outcome": "completed",
                "coverage_summary": (
                    "A matching offer was found, but exact-page verification "
                    "exhausted its bounded retry budget."
                ),
            }
        )

        self.assertIn(
            "SOURCE RESEARCH FINISHED",
            response,
            "A terminal failed candidate must not hold its source open forever.",
        )

    def test_product_ref_selection_failures_use_the_same_retry_budget(self):
        """
        Product ref-selection can fail before the generic validate_quote path.
        Those failures must still use the same shared candidate retry lifecycle.
        """
        query = "Logitech Superlight 2 mouse en ucuz fiyatını araştır"

        state = ComparisonState(
            query=query,
            category="product",
            target_product="Logitech Superlight 2",
            criteria=product_criteria(query),
            planned_sources=plan_sources(query),
        )
        store = ObservationStore()
        tools = {
            tool.name: tool
            for tool in create_research_tools(lambda: state, store)
        }

        tools["research_start_source"].invoke(
            {"source": "Google Shopping"}
        )

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
        bad_selection = {
            **SELECTION,
            "offer_ref": "f12e142",
        }

        first_observation = store.capture(URL, PAGE)
        first = tools["research_verify_product"].invoke(
            {
                "result_id": result.result_id,
                "observation_id": first_observation.observation_id,
                "selection": bad_selection,
                "final_check": False,
            }
        )

        self.assertIn("VERIFICATION BLOCKED", first)
        self.assertEqual(
            result.verification_status,
            VerificationStatus.PENDING,
        )

        for _ in range(4):
            observation = store.capture(URL, PAGE)
            tools["research_verify_product"].invoke(
                {
                    "result_id": result.result_id,
                    "observation_id": observation.observation_id,
                    "selection": bad_selection,
                    "final_check": False,
                }
            )
            if result.verification_status == VerificationStatus.BLOCKED:
                break

        self.assertEqual(
            result.verification_status,
            VerificationStatus.BLOCKED,
            "Product pre-validation failures must not bypass the generic retry guard.",
        )

        observation = store.capture(URL, PAGE)
        response = tools["research_verify_product"].invoke(
            {
                "result_id": result.result_id,
                "observation_id": observation.observation_id,
                "selection": SELECTION,
                "final_check": False,
            }
        )

        self.assertIn("VERIFICATION SKIPPED", response)

    def test_same_offer_is_idempotent_across_new_discovery_observations(self):
        """
        A new snapshot of the same exact offer must not create result_2/result_3/...
        and thereby bypass the retry budget.
        """
        state = ComparisonState(
            query="Compare offers",
            category="general",
            planned_sources=["Google Shopping"],
        )
        store = ObservationStore()
        tools = {
            tool.name: tool
            for tool in create_research_tools(lambda: state, store)
        }

        tools["research_start_source"].invoke(
            {"source": "Google Shopping"}
        )

        args = {
            "title": "Same Offer",
            "source": "Google Shopping",
            "seller": "Example Seller",
            "price": 1000,
            "currency": "TRY",
            "offer_url": "https://merchant.example/offer",
            "details": {"note": "same logical offer"},
        }

        first_observation = store.capture(
            "https://www.google.com/search?tbm=shop&q=same+offer",
            "Same Offer",
        )
        first = tools["research_add_result"].invoke(
            {
                **args,
                "url": first_observation.page_url,
                "observation_id": first_observation.observation_id,
            }
        )
        self.assertIn("STORED RESULT:", first)
        self.assertEqual(len(state.results), 1)

        second_observation = store.capture(
            first_observation.page_url,
            "Same Offer",
        )
        second = tools["research_add_result"].invoke(
            {
                **args,
                "url": second_observation.page_url,
                "observation_id": second_observation.observation_id,
            }
        )

        self.assertIn(
            "ALREADY EXISTS",
            second,
            "Observation IDs are evidence metadata, not offer identity.",
        )
        self.assertEqual(
            len(state.results),
            1,
            "The same logical offer must keep one durable result_id.",
        )

    def test_different_offer_urls_remain_distinct(self):
        """Deduplication must not merge genuinely different offers."""
        state = ComparisonState(
            query="Compare offers",
            category="general",
            planned_sources=["Google Shopping"],
        )
        store = ObservationStore()
        tools = {
            tool.name: tool
            for tool in create_research_tools(lambda: state, store)
        }

        tools["research_start_source"].invoke(
            {"source": "Google Shopping"}
        )

        for number in (1, 2):
            observation = store.capture(
                f"https://www.google.com/search?tbm=shop&q=offer{number}",
                "Same visible title",
            )
            response = tools["research_add_result"].invoke(
                {
                    "title": "Same visible title",
                    "source": "Google Shopping",
                    "seller": "Example Seller",
                    "price": 1000,
                    "currency": "TRY",
                    "url": observation.page_url,
                    "offer_url": f"https://merchant.example/offer/{number}",
                    "observation_id": observation.observation_id,
                }
            )
            self.assertIn("STORED RESULT:", response)

        self.assertEqual(len(state.results), 2)


if __name__ == "__main__":
    unittest.main()
