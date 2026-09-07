from typing import Callable

from langchain_core.tools import tool

from core.research.comparison_state import ComparisonState, ComparisonResult



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
        url: str | None = None,
        price: float | None = None,
        currency: str | None = None,
        details: dict | None = None,
    ) -> str:
        """Store one option found during comparison research."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        # Create a structured comparison result
        result = ComparisonResult(
            title=title.strip(),
            source=source.strip(),
            url=url,
            price=price,
            currency=currency,
            details=details or {},
        )

        # Store the result in the active research state
        state.add_result(result)

        return f"Stored research result: {result.title}"

    # Return all research tools
    return [
        research_status,
        research_mark_source_checked,
        research_add_result
    ]

    