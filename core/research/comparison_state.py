from dataclasses import dataclass, field
from typing import Any



# For one result
@dataclass
class ComparisonResult:
    # Name or title of the found option
    title: str

    # Website or source where the result was found
    source: str

    # Direct or relevant URL for user verification
    url: str | None = None

    # Price is optional because not every comparison is price-based
    price: float | None = None

    # Currency used for the price
    currency: str | None = None

    # Extra information that depends on the task
    details: dict[str, Any] = field(default_factory=dict)



@dataclass
class ComparisonState:
    # Original comparison request from the user
    query: str

    # Criteria used to compare the results
    criteria: dict[str, Any] = field(default_factory=dict)

    # Sources Jarvis plans to research
    planned_sources: list[str] = field(default_factory=list)

    # Sources Jarvis has already checked
    checked_sources: list[str] = field(default_factory=list)

    # Results collected during the research
    results: list[ComparisonResult] = field(default_factory=list)


    def mark_source_checked(self, source: str) -> None:
        # Avoid adding the same source more than once
        if source not in self.checked_sources:
            self.checked_sources.append(source)

    def add_result(self, result: ComparisonResult) -> None:
        # Store a result found during the research
        self.results.append(result)


    def coverage_complete(self) -> bool:
        # Research cannot be complete without planned sources
        if not self.planned_sources:
            return False

        # Research is complete only when every planned source was checked
        return all(
            source in self.checked_sources
            for source in self.planned_sources
        )