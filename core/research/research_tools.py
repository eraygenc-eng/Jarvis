from typing import Callable

from langchain_core.tools import tool

from core.research.comparison_state import ComparisonState, ComparisonResult, normalize_identity



def create_research_tools(
        get_state: Callable[[], ComparisonState | None],
) -> list:


    @tool
    def research_status() -> str:
        """Return the progress of the active comparison research."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        # Find sources that still need to be checked
        remaining_sources = [
            source
            for source in state.planned_sources
            if source not in state.checked_sources
        ]

        # Return the current research progress
        return (
            f"Planned sources: {state.planned_sources}\n"
            f"Checked sources: {state.checked_sources}\n"
            f"Remaining sources: {remaining_sources}\n"
            f"Collected results: {len(state.results)}\n"
            f"Coverage complete: {state.coverage_complete()}"
        )

    @tool
    def research_mark_source_checked(source: str) -> str:
        """Mark a planned research source as checked."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        # Clean the source name
        requested_source = source.strip()

        # Find the canonical source name from the research plan
        matched_source = next(
            (
                planned_source
                for planned_source in state.planned_sources
                if planned_source.casefold() == requested_source.casefold()
            ),
            None,
        )

        # Reject sources that are not part of the research plan
        if matched_source is None:
            return f"Source is not in the research plan: {source}"

        # Mark the source as checked
        state.mark_source_checked(matched_source)

        return f"Marked as checked: {matched_source}"
    

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
        details: dict | None = None,
    ) -> str:
        """Store one option found during comparison research."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        result = ComparisonResult(
            title=title.strip(),
            source=source.strip(),
            model=model.strip() if model else None,
            variant=variant.strip() if variant else None,
            sku=sku.strip() if sku else None,
            seller=seller.strip() if seller else None,
            regular_price=regular_price,
            price=price,
            price_condition=(
                price_condition.strip()
                if price_condition
                else None
            ),
            shipping_cost=shipping_cost,
            currency=currency,
            url=url,
            details=details or {},
        )

        # Collect identity warnings for similar results
        identity_warnings = []

        for existing_result in state.results:
            # Compare identity only when both results refer to the same model
            if result.model and existing_result.model:
                same_model = (
                    normalize_identity(result.model)
                    == normalize_identity(existing_result.model)
                )

                if not same_model:
                    continue

                identity_match = result.matches_identity(existing_result)

                # Warn when the same model has a different known SKU or variant
                if identity_match is False:
                    identity_warnings.append(
                        f"Possible variant mismatch with "
                        f"'{existing_result.title}' from "
                        f"{existing_result.source}."
                    )

                # Warn when exact identity cannot be verified
                elif identity_match is None:
                    identity_warnings.append(
                        f"Exact variant could not be verified against "
                        f"'{existing_result.title}' from "
                        f"{existing_result.source}."
                    )

        # Store the result in the active research state
        state.add_result(result)

        # Return warnings so the agent does not assume variants are identical
        if identity_warnings:
            warnings_text = " ".join(identity_warnings)

            return (
                f"Stored research result: {result.title}. "
                f"IDENTITY WARNING: {warnings_text}"
            )

        return f"Stored research result: {result.title}"

    # Return all research tools
    return [
        research_status,
        research_mark_source_checked,
        research_add_result
    ]

    