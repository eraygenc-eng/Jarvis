from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.research.research_utils import normalize_identity


class SourceStatus(str, Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    COMPLETED = "completed"
    NO_RESULTS = "no_results"
    BLOCKED = "blocked"


class StagingStatus(str, Enum):
    # This comparison does not need transaction staging
    NOT_REQUIRED = "not_required"

    # Staging should be attempted after finalization
    PENDING = "pending"

    # Browser reached a safe pre-commit transaction stage
    STAGED = "staged"

    # Staging could not continue safely
    BLOCKED = "blocked"



@dataclass
class SourceResearchState:
    # Canonical source name
    source: str

    # Current source research status
    status: SourceStatus = SourceStatus.PENDING

    # Results collected from this source
    result_ids: list[str] = field(default_factory=list)

    # Number of research attempts
    attempts: int = 0

    # Why research ended
    completion_reason: str | None = None

    # Best offers calculated by ranking.py
    best_public_result_id: str | None = None
    best_conditional_result_id: str | None = None

    def is_terminal(self) -> bool:
        return self.status in {
            SourceStatus.COMPLETED,
            SourceStatus.NO_RESULTS,
            SourceStatus.BLOCKED,
        }


@dataclass
class ComparisonResult:
    # Basic result information
    title: str
    source: str

    result_id: str | None = None

    # Verification
    verified: bool = False
    verification_notes: str | None = None
    verified_details: dict[str, Any] = field(
        default_factory=dict
    )
    verification_url: str | None = None

    # Identity
    model: str | None = None
    variant: str | None = None
    sku: str | None = None

    # Seller or provider
    seller: str | None = None

    # Pricing
    regular_price: float | None = None
    price: float | None = None
    price_condition: str | None = None
    shipping_cost: float | None = None
    currency: str | None = None

    # URLs
    url: str | None = None
    offer_url: str | None = None

    # Totals
    effective_total: float | None = None
    public_total: float | None = None
    conditional_total: float | None = None

    # Extra task-specific data
    details: dict[str, Any] = field(
        default_factory=dict
    )

    def matches_identity(
        self,
        other: "ComparisonResult",
    ) -> bool | None:
        # SKU is the strongest identity signal
        if self.sku and other.sku:
            return (
                normalize_identity(self.sku)
                == normalize_identity(other.sku)
            )

        # Different known models are not equal
        if self.model and other.model:
            if (
                normalize_identity(self.model)
                != normalize_identity(other.model)
            ):
                return False

        # Compare variants when available
        if self.variant and other.variant:
            return (
                normalize_identity(self.variant)
                == normalize_identity(other.variant)
            )

        return None


@dataclass
class ComparisonState:
    # Original user request
    query: str

    # Comparison criteria
    criteria: dict[str, Any] = field(
        default_factory=dict
    )

    # Planned research sources
    planned_sources: list[str] = field(
        default_factory=list
    )

    # Temporary compatibility field
    checked_sources: list[str] = field(
        default_factory=list
    )

    # All collected results
    results: list[ComparisonResult] = field(
        default_factory=list
    )

    # Per-source state
    source_states: dict[
        str,
        SourceResearchState,
    ] = field(default_factory=dict)

    # Final result
    finalized_result_id: str | None = None

    # Final browser location
    final_page_verified: bool = False
    final_page_url: str | None = None
    final_page_notes: str | None = None

    # Whether Jarvis should move toward checkout/booking after finalization
    requires_staging: bool = False

    # Transaction staging state
    staging_status: StagingStatus = StagingStatus.NOT_REQUIRED

    # Browser page where staging stopped
    staging_url: str | None = None

    # Type of stage reached, such as cart or checkout
    staging_type: str | None = None

    # Notes about the staging result
    staging_notes: str | None = None


    def __post_init__(self) -> None:
        # Create a state for every planned source
        for source in self.planned_sources:
            self.source_states.setdefault(
                source,
                SourceResearchState(source=source),
            )

        # Prepare final transaction staging
        if self.requires_staging:
            self.staging_status = StagingStatus.PENDING
        else:
            self.staging_status = StagingStatus.NOT_REQUIRED

    def get_source_state(
        self,
        source: str,
    ) -> SourceResearchState | None:
        requested = source.strip().casefold()

        return next(
            (
                source_state
                for name, source_state
                in self.source_states.items()
                if name.casefold() == requested
            ),
            None,
        )

    def start_source(
        self,
        source: str,
    ) -> bool:
        source_state = self.get_source_state(source)

        if source_state is None:
            return False

        if source_state.is_terminal():
            return False

        if source_state.status == SourceStatus.RESEARCHING:
            return False

        source_state.status = SourceStatus.RESEARCHING
        source_state.attempts += 1

        return True

    def complete_source(
        self,
        source: str,
        status: SourceStatus,
        reason: str | None = None,
    ) -> bool:
        source_state = self.get_source_state(source)

        if source_state is None:
            return False

        allowed_statuses = {
            SourceStatus.COMPLETED,
            SourceStatus.NO_RESULTS,
            SourceStatus.BLOCKED,
        }

        if status not in allowed_statuses:
            return False

        # Successful research must contain a result
        if (
            status == SourceStatus.COMPLETED
            and not source_state.result_ids
        ):
            return False

        source_state.status = status
        source_state.completion_reason = reason

        if source not in self.checked_sources:
            self.checked_sources.append(source)

        return True

    def add_result(
        self,
        result: ComparisonResult,
    ) -> None:
        if result.result_id is None:
            result.result_id = (
                f"result_{len(self.results) + 1}"
            )

        self.results.append(result)

        source_state = self.get_source_state(
            result.source
        )

        if source_state is not None:
            if (
                result.result_id
                not in source_state.result_ids
            ):
                source_state.result_ids.append(
                    result.result_id
                )

        # New information invalidates old final decisions
        self.reset_finalization()

    def get_result(
        self,
        result_id: str,
    ) -> ComparisonResult | None:
        return next(
            (
                result
                for result in self.results
                if result.result_id == result_id
            ),
            None,
        )

    def get_results_for_source(
        self,
        source: str,
    ) -> list[ComparisonResult]:
        source_state = self.get_source_state(source)

        if source_state is None:
            return []

        result_ids = set(source_state.result_ids)

        return [
            result
            for result in self.results
            if result.result_id in result_ids
        ]

    def get_verified_results(
        self,
    ) -> list[ComparisonResult]:
        return [
            result
            for result in self.results
            if result.verified
        ]

    def has_verified_results(self) -> bool:
        return bool(self.get_verified_results())

    def get_verified_result(
        self,
        result_id: str,
    ) -> ComparisonResult | None:
        result = self.get_result(result_id)

        if result is None or not result.verified:
            return None

        return result

    def coverage_complete(self) -> bool:
        if not self.planned_sources:
            return False

        return all(
            source_state.is_terminal()
            for source_state
            in self.source_states.values()
        )

    def is_finalized(self) -> bool:
        if self.finalized_result_id is None:
            return False

        return (
            self.get_verified_result(
                self.finalized_result_id
            )
            is not None
        )


    def staging_finished(self) -> bool:
        # No staging is needed for this task
        if not self.requires_staging:
            return True

        # Staging can finish successfully or stop safely
        return self.staging_status in {
            StagingStatus.STAGED,
            StagingStatus.BLOCKED,
        }


    def confirm_staging(
        self,
        url: str,
        staging_type: str,
        notes: str | None = None,
    ) -> None:
        self.staging_status = StagingStatus.STAGED
        self.staging_url = url
        self.staging_type = staging_type
        self.staging_notes = notes


    def block_staging(
        self,
        reason: str,
    ) -> None:
        self.staging_status = StagingStatus.BLOCKED
        self.staging_notes = reason
    

    def is_ready_to_return(self) -> bool:
        return (
            self.is_finalized()
            and self.final_page_verified
            and self.staging_finished()
        )

    def reset_finalization(self) -> None:
        self.finalized_result_id = None

        # Reset final verified page
        self.final_page_verified = False
        self.final_page_url = None
        self.final_page_notes = None

        # Reset transaction staging
        self.staging_url = None
        self.staging_type = None
        self.staging_notes = None

        if self.requires_staging:
            self.staging_status = StagingStatus.PENDING
        else:
            self.staging_status = StagingStatus.NOT_REQUIRED