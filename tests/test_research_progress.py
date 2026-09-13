import unittest

from core.research.comparison_state import (
    ComparisonResult,
    ComparisonState,
    SourceStatus,
    VerificationStatus,
)
from core.research.progress import (
    MAX_PENDING_RESULTS,
    build_research_progress,
    render_research_progress,
)


def make_result(
    *,
    title="Offer",
    source="Source",
    seller="Seller",
    currency="TRY",
    public_total=5000,
    verified=False,
    verification_status=VerificationStatus.PENDING,
):
    return ComparisonResult(
        title=title,
        source=source,
        seller=seller,
        currency=currency,
        public_total=public_total,
        verified=verified,
        verification_status=verification_status,
        offer_url=f"https://example.com/{title}",
        price_scope="total",
        fees_included=True,
    )


class ResearchProgressTests(unittest.TestCase):

    def test_researching_source_is_continued_not_restarted(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=[
                "Completed",
                "Active",
                "Next",
                "Blocked",
            ],
        )

        state.get_source_state(
            "Completed"
        ).status = SourceStatus.NO_RESULTS

        state.get_source_state(
            "Active"
        ).status = SourceStatus.RESEARCHING

        state.get_source_state(
            "Next"
        ).status = SourceStatus.PENDING

        state.get_source_state(
            "Blocked"
        ).status = SourceStatus.BLOCKED

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"],
            {
                "action": "continue_source",
                "source": "Active",
            },
        )

    def test_next_pending_source_is_started(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=[
                "Done",
                "Next",
                "Later",
            ],
        )

        state.get_source_state(
            "Done"
        ).status = SourceStatus.NO_RESULTS

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"],
            {
                "action": "start_source",
                "source": "Next",
            },
        )

    def test_terminal_sources_are_not_selected_again(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=[
                "Completed",
                "Empty",
                "Blocked",
                "Remaining",
            ],
        )

        state.get_source_state(
            "Completed"
        ).status = SourceStatus.COMPLETED

        state.get_source_state(
            "Empty"
        ).status = SourceStatus.NO_RESULTS

        state.get_source_state(
            "Blocked"
        ).status = SourceStatus.BLOCKED

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"]["action"],
            "start_source",
        )

        self.assertEqual(
            progress["next_action"]["source"],
            "Remaining",
        )

    def test_pending_offer_is_selected_after_source_coverage(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=["Shop"],
        )

        result = make_result(
            source="Shop",
            seller="Example seller",
        )

        state.add_result(result)

        state.get_source_state(
            "Shop"
        ).status = SourceStatus.COMPLETED

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"]["action"],
            "verify_result",
        )

        self.assertEqual(
            progress["next_action"]["result_id"],
            result.result_id,
        )

        self.assertEqual(
            progress["next_action"]["source"],
            "Shop",
        )

    def test_final_decision_is_requested_after_verifications(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=["Shop"],
        )

        result = make_result(
            source="Shop",
            verified=True,
            verification_status=(
                VerificationStatus.VERIFIED
            ),
        )

        state.add_result(result)

        state.get_source_state(
            "Shop"
        ).status = SourceStatus.COMPLETED

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"],
            {
                "action": "resolve_final_decision",
            },
        )

    def test_final_page_is_next_after_finalization(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=["Shop"],
        )

        result = make_result(
            source="Shop",
            verified=True,
            verification_status=(
                VerificationStatus.VERIFIED
            ),
        )

        state.add_result(result)

        state.get_source_state(
            "Shop"
        ).status = SourceStatus.COMPLETED

        state.finalized_result_id = result.result_id

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"]["action"],
            "verify_final_page",
        )

        self.assertEqual(
            progress["next_action"]["result"][
                "result_id"
            ],
            result.result_id,
        )

    def test_ready_research_returns_ready_for_report(self):
        state = ComparisonState(
            query="Find the cheapest product",
            planned_sources=["Shop"],
        )

        result = make_result(
            source="Shop",
            verified=True,
            verification_status=(
                VerificationStatus.VERIFIED
            ),
        )

        state.add_result(result)

        state.get_source_state(
            "Shop"
        ).status = SourceStatus.COMPLETED

        state.finalized_result_id = result.result_id
        state.final_page_verified = True

        self.assertTrue(
            state.is_ready_to_return()
        )

        progress = build_research_progress(state)

        self.assertEqual(
            progress["next_action"],
            {
                "action": "ready_for_report",
            },
        )

    def test_pending_results_are_limited_in_model_view(self):
        state = ComparisonState(
            query="Compare offers",
            planned_sources=["Shop"],
        )

        total_results = MAX_PENDING_RESULTS + 4

        for number in range(total_results):
            state.add_result(
                make_result(
                    title=f"Offer-{number}",
                    source="Shop",
                )
            )

        progress = build_research_progress(state)

        pending = progress[
            "pending_verifications"
        ]

        self.assertEqual(
            pending["count"],
            total_results,
        )

        self.assertEqual(
            len(pending["items"]),
            MAX_PENDING_RESULTS,
        )

    def test_verified_public_prices_are_grouped_by_currency(self):
        state = ComparisonState(
            query="Compare prices",
        )

        state.add_result(
            make_result(
                title="TRY expensive",
                currency="TRY",
                public_total=6000,
                verified=True,
                verification_status=(
                    VerificationStatus.VERIFIED
                ),
            )
        )

        state.add_result(
            make_result(
                title="TRY cheap",
                currency="TRY",
                public_total=5000,
                verified=True,
                verification_status=(
                    VerificationStatus.VERIFIED
                ),
            )
        )

        state.add_result(
            make_result(
                title="USD offer",
                currency="USD",
                public_total=200,
                verified=True,
                verification_status=(
                    VerificationStatus.VERIFIED
                ),
            )
        )

        progress = build_research_progress(state)

        best = {
            item["currency"]: item["total"]
            for item
            in progress[
                "best_verified_public_by_currency"
            ]
        }

        self.assertEqual(
            best["TRY"],
            5000,
        )

        self.assertEqual(
            best["USD"],
            200,
        )

    def test_rendered_progress_is_compact_json(self):
        state = ComparisonState(
            query="Logitech Superlight 2 araştır",
            planned_sources=["Shop"],
        )

        rendered = render_research_progress(state)

        self.assertIn(
            '"original_request":'
            '"Logitech Superlight 2 araştır"',
            rendered,
        )

        self.assertIn(
            '"next_action":',
            rendered,
        )

        # Compact JSON should not contain pretty-print newlines.
        self.assertNotIn(
            "\n",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()