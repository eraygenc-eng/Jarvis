from dataclasses import dataclass, field
from typing import Any


def normalize_identity(value: str) -> str:
    # Normalize identifiers for reliable comparison
    return "".join(
        character
        for character in value.casefold().strip()
        if character.isalnum()
    )



# For one result
@dataclass
class ComparisonResult:
    # Name or title of the found option
    title: str

    # Website or source where the result was found
    source: str

    # Product or item model when available
    model: str | None = None

    # Specific configuration or variation of the item
    variant: str | None = None

    # SKU or another exact product identifier
    sku: str | None = None

    # Seller or provider offering the result
    seller: str | None = None

    # Normal price without special membership or discount conditions
    regular_price: float | None = None

    # Condition required to get the stored offer price
    price_condition: str | None = None

    # Shipping or additional delivery cost
    shipping_cost: float | None = None

    # Direct or relevant URL for user verification
    url: str | None = None

    # Best available price for this specific offer
    price: float | None = None

    # Currency used for the price
    currency: str | None = None

    # Extra information that depends on the task
    details: dict[str, Any] = field(default_factory=dict)


    def matches_identity(
        self,
        other: "ComparisonResult",
    ) -> bool | None:
        # Use SKU as the strongest identity signal
        if self.sku and other.sku:
            return (
                normalize_identity(self.sku)
                == normalize_identity(other.sku)
            )

        # Different known models are not the same item
        if self.model and other.model:
            if (
                normalize_identity(self.model)
                != normalize_identity(other.model)
            ):
                return False

        # Compare variants when both are available
        if self.variant and other.variant:
            return (
                normalize_identity(self.variant)
                == normalize_identity(other.variant)
            )

        # There is not enough information for an exact decision
        return None



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