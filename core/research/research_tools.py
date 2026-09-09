from typing import Callable

from langchain_core.tools import tool

from core.research.comparison_state import (
    ComparisonResult,
    ComparisonState,
    SourceStatus,
)
from core.research.ranking import (
    find_best_conditional,
    find_best_overall,
    find_best_public,
    get_conditional_total,
    get_public_total,
    refresh_source_rankings,
)
from core.research.research_utils import (
    get_canonical_source,
    is_price_focused_query,
)
from core.research.verification import (
    urls_match,
    validate_money_values,
)


def create_research_tools(
    get_state: Callable[
        [],
        ComparisonState | None,
    ],
) -> list:

    def describe_result(
        result: ComparisonResult | None,
    ) -> str:
        if result is None:
            return "None"

        return (
            f"{result.result_id} | "
            f"{result.title} | "
            f"source={result.source} | "
            f"public={get_public_total(result)} | "
            f"conditional="
            f"{get_conditional_total(result)} | "
            f"condition={result.price_condition} | "
            f"verified={result.verified}"
        )

    @tool
    def research_status() -> str:
        """Return the progress of active comparison research."""

        state = get_state()

        if state is None:
            return "No active comparison research."

        source_lines = []

        for source in state.planned_sources:
            source_state = state.get_source_state(source)

            if source_state is None:
                continue

            source_lines.append(
                f"- {source}: "
                f"{source_state.status.value}, "
                f"results={len(source_state.result_ids)}, "
                f"best_public="
                f"{source_state.best_public_result_id}, "
                f"best_conditional="
                f"{source_state.best_conditional_result_id}"
            )

        remaining = [
            source
            for source in state.planned_sources
            if (
                state.get_source_state(source)
                is not None
                and not state
                .get_source_state(source)
                .is_terminal()
            )
        ]

        return (
            f"Coverage complete: "
            f"{state.coverage_complete()}\n"
            f"Remaining sources: {remaining}\n"
            f"Results: {len(state.results)}\n"
            f"Verified results: "
            f"{len(state.get_verified_results())}\n"
            f"Finalized: {state.is_finalized()}\n"
            f"Final page verified: "
            f"{state.final_page_verified}\n"
            f"Staging required: "
            f"{state.requires_staging}\n"
            f"Staging status: "
            f"{state.staging_status.value}\n"
            f"Ready to return: "
            f"{state.is_ready_to_return()}\n\n"
            + "\n".join(source_lines)
        )

    @tool
    def research_start_source(
        source: str,
    ) -> str:
        """Start researching one planned source."""

        state = get_state()

        if state is None:
            return (
                "SOURCE START BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                f"SOURCE START BLOCKED: "
                f"{source} is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if source_state is None:
            return "SOURCE START BLOCKED."

        if source_state.is_terminal():
            return (
                f"SOURCE ALREADY FINISHED: "
                f"{canonical_source}"
            )

        if (
            source_state.status
            == SourceStatus.RESEARCHING
        ):
            return (
                f"SOURCE ALREADY RESEARCHING: "
                f"{canonical_source}"
            )

        if not state.start_source(canonical_source):
            return (
                f"SOURCE START BLOCKED: "
                f"{canonical_source}"
            )

        return (
            f"SOURCE RESEARCH STARTED: "
            f"{canonical_source}"
        )

    @tool
    def research_add_result(
        title: str,
        source: str,
        model: str | None = None,
        variant: str | None = None,
        sku: str | None = None,
        seller: str | None = None,
        regular_price: float | None = None,
        price: float | None = None,
        price_condition: str | None = None,
        shipping_cost: float | None = None,
        currency: str | None = None,
        url: str | None = None,
        offer_url: str | None = None,
        effective_total: float | None = None,
        public_total: float | None = None,
        conditional_total: float | None = None,
        details: dict | None = None,
    ) -> str:
        """Store one offer found on the active source."""

        state = get_state()

        if state is None:
            return (
                "RESULT BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                f"RESULT BLOCKED: "
                f"{source} is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if (
            source_state is None
            or source_state.status
            != SourceStatus.RESEARCHING
        ):
            return (
                "RESULT BLOCKED: "
                "Call research_start_source first."
            )

        money_error = validate_money_values(
            regular_price=regular_price,
            price=price,
            shipping_cost=shipping_cost,
            effective_total=effective_total,
            public_total=public_total,
            conditional_total=conditional_total,
        )

        if money_error:
            return (
                f"RESULT BLOCKED: {money_error}"
            )

        if (
            conditional_total is not None
            and not price_condition
        ):
            return (
                "RESULT BLOCKED: "
                "conditional_total requires "
                "price_condition."
            )

        result = ComparisonResult(
            title=title.strip(),
            source=canonical_source,
            model=model.strip() if model else None,
            variant=(
                variant.strip()
                if variant
                else None
            ),
            sku=sku.strip() if sku else None,
            seller=(
                seller.strip()
                if seller
                else None
            ),
            regular_price=regular_price,
            price=price,
            price_condition=(
                price_condition.strip()
                if price_condition
                else None
            ),
            shipping_cost=shipping_cost,
            currency=(
                currency.strip()
                if currency
                else None
            ),
            url=url.strip() if url else None,
            offer_url=(
                offer_url.strip()
                if offer_url
                else None
            ),
            effective_total=effective_total,
            public_total=public_total,
            conditional_total=conditional_total,
            details=details or {},
        )

        state.add_result(result)

        refresh_source_rankings(
            state,
            canonical_source,
        )

        source_state = state.get_source_state(
            canonical_source
        )

        return (
            f"STORED RESULT: {result.title} "
            f"(result_id={result.result_id})\n"
            f"Source public best: "
            f"{source_state.best_public_result_id}\n"
            f"Source conditional best: "
            f"{source_state.best_conditional_result_id}"
        )

    @tool
    def research_complete_source(
        source: str,
        outcome: str,
        coverage_summary: str,
    ) -> str:
        """
        Finish one source.

        outcome:
        completed, no_results, or blocked.
        """

        state = get_state()

        if state is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Source is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if (
            source_state is None
            or source_state.status
            != SourceStatus.RESEARCHING
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Source is not being researched."
            )

        status_map = {
            "completed": SourceStatus.COMPLETED,
            "no_results": SourceStatus.NO_RESULTS,
            "blocked": SourceStatus.BLOCKED,
        }

        status = status_map.get(
            outcome.strip().lower()
        )

        if status is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Invalid outcome."
            )

        summary = coverage_summary.strip()

        if not summary:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "coverage_summary is required."
            )

        if (
            status == SourceStatus.COMPLETED
            and not source_state.result_ids
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "A completed source needs "
                "at least one stored result."
            )

        if (
            status == SourceStatus.NO_RESULTS
            and source_state.result_ids
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Stored results already exist."
            )

        if not state.complete_source(
            canonical_source,
            status,
            summary,
        ):
            return "SOURCE COMPLETION BLOCKED."

        return (
            f"SOURCE RESEARCH FINISHED: "
            f"{canonical_source}\n"
            f"Status: {status.value}\n"
            f"Results: "
            f"{len(source_state.result_ids)}"
        )

    @tool
    def research_mark_source_checked(
        source: str,
    ) -> str:
        """Deprecated source completion tool."""

        return (
            "DEPRECATED TOOL: "
            "Use research_start_source before browsing "
            "and research_complete_source when finished."
        )

    @tool
    def research_set_offer_url(
        result_id: str,
        offer_url: str,
    ) -> str:
        """Store the direct seller or provider URL."""

        state = get_state()

        if state is None:
            return "No active comparison research."

        result = state.get_result(result_id.strip())

        if result is None:
            return (
                f"Research result not found: "
                f"{result_id}"
            )

        result.offer_url = offer_url.strip()

        state.reset_finalization()

        return (
            f"Stored direct offer URL for "
            f"{result.result_id}."
        )

    @tool
    def research_verify_result(
        result_id: str,
        verification_url: str,
        verification_type: str,
        verification_notes: str | None = None,
        price: float | None = None,
        regular_price: float | None = None,
        price_condition: str | None = None,
        seller: str | None = None,
        shipping_cost: float | None = None,
        currency: str | None = None,
        variant: str | None = None,
        sku: str | None = None,
        effective_total: float | None = None,
        public_total: float | None = None,
        conditional_total: float | None = None,
        verified_details: dict | None = None,
    ) -> str:
        """Verify a result on its exact offer page."""

        state = get_state()

        if state is None:
            return (
                "VERIFICATION BLOCKED: "
                "No active comparison research."
            )

        result = state.get_result(
            result_id.strip()
        )

        if result is None:
            return (
                "VERIFICATION BLOCKED: "
                "Result not found."
            )

        if (
            verification_type.strip().lower()
            != "exact_offer"
        ):
            return (
                "VERIFICATION BLOCKED: "
                "Exact offer page required."
            )

        verification_url = (
            verification_url.strip()
        )

        if (
            result.offer_url
            and not urls_match(
                result.offer_url,
                verification_url,
            )
        ):
            return (
                "VERIFICATION BLOCKED: "
                "Current page does not match "
                "the stored offer URL."
            )

        money_error = validate_money_values(
            price=price,
            regular_price=regular_price,
            shipping_cost=shipping_cost,
            effective_total=effective_total,
            public_total=public_total,
            conditional_total=conditional_total,
        )

        if money_error:
            return (
                f"VERIFICATION BLOCKED: "
                f"{money_error}"
            )

        state.reset_finalization()

        if price is not None:
            result.price = price

        if regular_price is not None:
            result.regular_price = regular_price

        if price_condition is not None:
            condition = price_condition.strip()

            result.price_condition = (
                condition if condition else None
            )

        if seller is not None:
            result.seller = seller.strip()

        if shipping_cost is not None:
            result.shipping_cost = shipping_cost

        if currency is not None:
            result.currency = currency.strip()

        if variant is not None:
            result.variant = variant.strip()

        if sku is not None:
            result.sku = sku.strip()

        if effective_total is not None:
            result.effective_total = effective_total

        if public_total is not None:
            result.public_total = public_total

        if conditional_total is not None:
            result.conditional_total = (
                conditional_total
            )

        if verified_details is not None:
            result.verified_details = (
                verified_details.copy()
            )

        result.verified = True
        result.verification_url = (
            verification_url
        )

        result.verification_notes = (
            verification_notes.strip()
            if verification_notes
            else None
        )

        refresh_source_rankings(
            state,
            result.source,
        )

        return (
            f"VERIFIED RESULT: "
            f"{result.result_id}\n"
            f"Public total: "
            f"{get_public_total(result)}\n"
            f"Conditional total: "
            f"{get_conditional_total(result)}"
        )

    @tool
    def research_rankings(
        verified_only: bool = False,
    ) -> str:
        """Return Python-calculated comparison rankings."""

        state = get_state()

        if state is None:
            return "No active comparison research."

        public = find_best_public(
            state,
            verified_only,
        )

        conditional = find_best_conditional(
            state,
            verified_only,
        )

        overall = find_best_overall(
            state,
            verified_only,
        )

        return (
            f"Best public:\n"
            f"{describe_result(public)}\n\n"
            f"Best conditional:\n"
            f"{describe_result(conditional)}\n\n"
            f"Best overall:\n"
            f"{describe_result(overall)}"
        )

    @tool
    def research_finalize(
        result_id: str,
    ) -> str:
        """Finalize the verified winner."""

        state = get_state()

        if state is None:
            return (
                "FINALIZATION BLOCKED: "
                "No active research."
            )

        if not state.coverage_complete():
            return (
                "FINALIZATION BLOCKED: "
                "Research coverage is incomplete."
            )

        winner = state.get_verified_result(
            result_id.strip()
        )

        if winner is None:
            return (
                "FINALIZATION BLOCKED: "
                "Winner is not verified."
            )

        if is_price_focused_query(state.query):
            cheapest = find_best_overall(
                state,
                verified_only=True,
                strict=True,
            )

            if cheapest is None:
                return (
                    "FINALIZATION BLOCKED: "
                    "Verified final totals are "
                    "not sufficient for a reliable "
                    "price winner."
                )

            if (
                winner.result_id
                != cheapest.result_id
            ):
                return (
                    "FINALIZATION BLOCKED: "
                    f"Python ranking selected "
                    f"{cheapest.result_id}, "
                    f"not {winner.result_id}."
                )

        state.finalized_result_id = (
            winner.result_id
        )

        state.final_page_verified = False
        state.final_page_url = None
        state.final_page_notes = None

        return (
            f"FINALIZATION APPROVED: "
            f"{winner.result_id}"
        )

    @tool
    def research_confirm_final_page(
        result_id: str,
        final_page_url: str,
        final_page_notes: str | None = None,
    ) -> str:
        """Confirm the browser is on the winner page."""

        state = get_state()

        if state is None:
            return (
                "FINAL PAGE BLOCKED: "
                "No active research."
            )

        if not state.is_finalized():
            return (
                "FINAL PAGE BLOCKED: "
                "Research is not finalized."
            )

        if (
            state.finalized_result_id
            != result_id.strip()
        ):
            return (
                "FINAL PAGE BLOCKED: "
                "Wrong result."
            )

        winner = state.get_verified_result(
            state.finalized_result_id
        )

        if (
            winner is None
            or winner.verification_url is None
        ):
            return (
                "FINAL PAGE BLOCKED: "
                "Winner has no verification URL."
            )

        final_page_url = final_page_url.strip()

        if not urls_match(
            winner.verification_url,
            final_page_url,
        ):
            return (
                "FINAL PAGE BLOCKED: "
                "Browser is not on the "
                "verified winner page."
            )

        state.final_page_verified = True
        state.final_page_url = final_page_url

        state.final_page_notes = (
            final_page_notes.strip()
            if final_page_notes
            else None
        )

        return (
            f"FINAL PAGE CONFIRMED: "
            f"{result_id}"
        )

    @tool
    def research_confirm_staging_page(
        result_id: str,
        staging_url: str,
        staging_type: str,
        staging_notes: str | None = None,
    ) -> str:
        """
        Confirm that the browser reached a safe transaction stage
        before payment or irreversible confirmation.
        """

        state = get_state()

        if state is None:
            return (
                "STAGING BLOCKED: "
                "No active comparison research."
            )

        if not state.requires_staging:
            return (
                "STAGING NOT REQUIRED: "
                "This comparison does not require "
                "transaction staging."
            )

        if not state.is_finalized():
            return (
                "STAGING BLOCKED: "
                "Research must be finalized first."
            )

        if not state.final_page_verified:
            return (
                "STAGING BLOCKED: "
                "The finalized offer page must be "
                "confirmed before staging."
            )

        if (
            state.finalized_result_id
            != result_id.strip()
        ):
            return (
                "STAGING BLOCKED: "
                "This result is not the finalized winner."
            )

        allowed_types = {
            "cart",
            "checkout",
            "booking_details",
            "reservation_details",
            "passenger_details",
            "review",
        }

        normalized_type = staging_type.strip().lower()

        if normalized_type not in allowed_types:
            return (
                "STAGING BLOCKED: "
                "Unsupported staging type."
            )

        cleaned_url = staging_url.strip()

        if not cleaned_url:
            return (
                "STAGING BLOCKED: "
                "Staging URL is empty."
            )

        state.confirm_staging(
            url=cleaned_url,
            staging_type=normalized_type,
            notes=(
                staging_notes.strip()
                if staging_notes
                else None
            ),
        )

        return (
            f"STAGING CONFIRMED: "
            f"{normalized_type} at {cleaned_url}"
        )


    @tool
    def research_mark_staging_blocked(
        result_id: str,
        reason: str,
    ) -> str:
        """
        Mark staging as safely blocked when Jarvis cannot
        continue without sensitive information or unsafe actions.
        """

        state = get_state()

        if state is None:
            return (
                "STAGING BLOCKED: "
                "No active comparison research."
            )

        if not state.requires_staging:
            return "STAGING NOT REQUIRED."

        if not state.is_finalized():
            return (
                "STAGING BLOCKED: "
                "Research must be finalized first."
            )

        if (
            state.finalized_result_id
            != result_id.strip()
        ):
            return (
                "STAGING BLOCKED: "
                "This result is not the finalized winner."
            )

        cleaned_reason = reason.strip()

        if not cleaned_reason:
            return (
                "STAGING BLOCKED: "
                "A reason is required."
            )

        state.block_staging(cleaned_reason)

        return (
            f"STAGING SAFELY STOPPED: "
            f"{cleaned_reason}"
        )

    return [
        research_status,
        research_start_source,
        research_add_result,
        research_complete_source,
        research_mark_source_checked,
        research_set_offer_url,
        research_verify_result,
        research_rankings,
        research_finalize,
        research_confirm_final_page,
        research_confirm_staging_page,
        research_mark_staging_blocked
    ]