from core.research.comparison_state import ComparisonState
from core.research.source_planner import plan_sources


def create_comparison_state(prompt: str) -> ComparisonState:
    # Plan the initial sources for the comparison
    sources = plan_sources(prompt)

    # Create a new state for the research task
    return ComparisonState(
        query=prompt,
        planned_sources=sources,
    )