from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any

from core.research.research_utils import normalize_identity


# Generic verification loop guard shared by every research category.
MAX_VERIFICATION_ATTEMPTS = 4
MAX_SAME_VERIFICATION_FAILURES = 2

# Final-page confirmation has a separate retry lifecycle.
# A bad final evidence selection must never destroy a previously verified offer.
MAX_FINAL_PAGE_ATTEMPTS = 4
MAX_SAME_FINAL_PAGE_FAILURES = 2


class SourceStatus(str, Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    COMPLETED = "completed"
    NO_RESULTS = "no_results"
    BLOCKED = "blocked"
    LIMIT_REACHED = "limit_reached"


class VerificationStatus(str, Enum):
    # The offer still needs verification.
    PENDING = "pending"

    # The exact offer was verified.
    VERIFIED = "verified"

    # Verification was attempted but could not be completed.
    BLOCKED = "blocked"

    # The offer was checked and found unsuitable.
    REJECTED = "rejected"


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

    # Number of model cycles spent on this source
    model_cycles: int = 0

    # Search queries actually tried while discovering offers on this source
    discovery_queries: list[str] = field(default_factory=list)

    # Optional notes about each discovery attempt
    discovery_notes: list[str] = field(default_factory=list)
    discovery_evidence: list[dict[str, Any]] = field(default_factory=list)

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
            SourceStatus.LIMIT_REACHED,
        }

    def record_discovery_attempt(
    self,
    query: str,
    note: str | None = None,
    ) -> bool:
        cleaned_query = " ".join(query.split()).strip()

        if not cleaned_query:
            return False

        normalized_query = normalize_identity(cleaned_query)

        existing_queries = {
            normalize_identity(existing_query)
            for existing_query in self.discovery_queries
        }

        # Do not count the same search twice
        if normalized_query in existing_queries:
            return False

        self.discovery_queries.append(cleaned_query)

        if note:
            self.discovery_notes.append(note.strip())
        else:
            self.discovery_notes.append("")

        return True


    def discovery_attempt_count(self) -> int:
        return len(self.discovery_queries)


    def record_model_cycle(self, max_cycles: int) -> bool:
        # Stop this source when its model-cycle budget is exhausted
        if self.model_cycles >= max_cycles:
            return False

        self.model_cycles += 1
        return True


@dataclass
class ComparisonResult:
    # Basic result information
    title: str
    source: str

    result_id: str | None = None

    # Verification
    verified: bool = False

    # Track verification separately from source research.
    verification_status: VerificationStatus = VerificationStatus.PENDING

    # Bounded verification lifecycle. These fields are category-independent and
    # apply to products, flights, hotels, rentals and other offer types.
    verification_attempts: int = 0
    verification_failure_counts: dict[str, int] = field(default_factory=dict)
    last_verification_failure: str | None = None

    # Explain why verification was blocked or the offer was rejected.
    verification_reason: str | None = None
    verification_notes: str | None = None
    verified_details: dict[str, Any] = field(
        default_factory=dict
    )
    verification_url: str | None = None

    # Identify the browser observation used for verification.
    verification_observation_id: str | None = None

    # Preserve the exact excerpt used as price evidence.
    verification_price_evidence: str | None = None

    # Keep discovery and subsequent price changes available to the report.
    price_history: list[dict[str, Any]] = field(default_factory=list)
    verification_offer_ref: str | None = None
    verification_identity_evidence: str | None = None
    verification_seller_evidence: str | None = None

    # A comparable quote covers the complete requested purchase/stay/trip/rental.
    price_scope: str = "unknown"
    scope_evidence: str | None = None
    mandatory_fees: float | None = None
    fees_included: bool = False

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

    def invalidate_verification(self) -> None:
        """Clear verification while retaining observed offer data."""

        self.verified = False
        self.verification_status = VerificationStatus.PENDING
        self.verification_reason = None
        self.verification_url = None
        self.verification_observation_id = None
        self.verification_price_evidence = None
        self.verification_offer_ref = None
        self.verification_identity_evidence = None
        self.verification_seller_evidence = None
        self.verification_notes = None
        self.verified_details = {}

    def reset_verification_retry(self) -> None:
        """Start a fresh retry epoch after a successful quote or URL correction."""
        self.verification_attempts = 0
        self.verification_failure_counts.clear()
        self.last_verification_failure = None

    def verification_is_terminal(self) -> bool:
        return self.verification_status in {
            VerificationStatus.BLOCKED,
            VerificationStatus.REJECTED,
        }

    @staticmethod
    def _verification_failure_key(reason: str) -> str:
        # Snapshot refs and observation IDs change between fresh captures. They
        # must not make the same logical failure look new to the retry guard.
        key = " ".join(reason.split()).strip().casefold()
        key = re.sub(r"\bf\d+e\d+\b", "<ref>", key)
        key = re.sub(
            r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
            "<observation>",
            key,
        )
        return key or "unknown verification failure"

    def record_verification_failure(self, reason: str) -> bool:
        """Record one failed evidence check and return True when terminal.

        A repeated evidence/quote failure may be corrected once, but it cannot
        keep one candidate PENDING forever. The same lifecycle is used by every
        research category.
        """
        cleaned_reason = " ".join(reason.split()).strip()
        failure_key = self._verification_failure_key(cleaned_reason)

        self.verification_attempts += 1
        self.last_verification_failure = cleaned_reason
        self.verification_reason = cleaned_reason
        self.verified = False

        same_failure_count = self.verification_failure_counts.get(failure_key, 0) + 1
        self.verification_failure_counts[failure_key] = same_failure_count

        terminal = (
            self.verification_attempts >= MAX_VERIFICATION_ATTEMPTS
            or same_failure_count >= MAX_SAME_VERIFICATION_FAILURES
        )

        self.verification_status = (
            VerificationStatus.BLOCKED
            if terminal
            else VerificationStatus.PENDING
        )

        return terminal


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

    category: str = "general"

    # Clean product identity extracted from the request
    target_product: str | None = None

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
    finished_without_winner_reason: str | None = None

    # Final browser location
    final_page_verified: bool = False
    final_page_url: str | None = None
    final_page_notes: str | None = None
    final_page_observation_id: str | None = None

    # Final-page confirmation is isolated from candidate verification.
    final_page_attempts: int = 0
    final_page_failure_counts: dict[str, int] = field(default_factory=dict)
    final_page_last_failure: str | None = None
    final_page_blocked: bool = False
    final_page_block_reason: str | None = None

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


    def get_researching_source_state(
        self,
    ) -> SourceResearchState | None:
        # Only one source should be researched at a time
        for source in self.planned_sources:
            source_state = self.get_source_state(source)

            if (
                source_state is not None
                and source_state.status == SourceStatus.RESEARCHING
            ):
                return source_state

        return None
    

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

        # Do not research multiple sources at the same time
        active_source = self.get_researching_source_state()

        if (
            active_source is not None
            and active_source.source.casefold()
            != source_state.source.casefold()
        ):
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
            SourceStatus.LIMIT_REACHED
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
            if result.verified and result.verification_status == VerificationStatus.VERIFIED
        ]

    def has_verified_results(self) -> bool:
        return bool(self.get_verified_results())

    def get_verified_result(
        self,
        result_id: str,
    ) -> ComparisonResult | None:
        result = self.get_result(result_id)

        if result is None or not result.verified or result.verification_status != VerificationStatus.VERIFIED:
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
    

    def reset_final_page_retry(self) -> None:
        """Start a fresh final-confirmation retry epoch."""
        self.final_page_attempts = 0
        self.final_page_failure_counts.clear()
        self.final_page_last_failure = None
        self.final_page_blocked = False
        self.final_page_block_reason = None

    def record_final_page_failure(self, reason: str) -> bool:
        """Record final-page evidence failure without touching the winner."""
        cleaned_reason = " ".join(reason.split()).strip()
        failure_key = ComparisonResult._verification_failure_key(cleaned_reason)

        self.final_page_attempts += 1
        self.final_page_last_failure = cleaned_reason
        self.final_page_verified = False
        self.final_page_url = None
        self.final_page_observation_id = None
        self.final_page_notes = None

        same_failure_count = self.final_page_failure_counts.get(failure_key, 0) + 1
        self.final_page_failure_counts[failure_key] = same_failure_count

        terminal = (
            self.final_page_attempts >= MAX_FINAL_PAGE_ATTEMPTS
            or same_failure_count >= MAX_SAME_FINAL_PAGE_FAILURES
        )

        self.final_page_blocked = terminal
        self.final_page_block_reason = cleaned_reason if terminal else None
        return terminal

    def is_ready_to_return(self) -> bool:
        pending_exists = any(
            result.verification_status == VerificationStatus.PENDING
            for result in self.results
        )

        if not self.coverage_complete() or pending_exists:
            return False

        if not self.has_verified_results():
            return True

        if self.finished_without_winner_reason:
            return True

        if not self.is_finalized():
            return False

        # Final confirmation may end safely without destroying the verified winner.
        if self.final_page_blocked:
            return True

        return (
            self.final_page_verified
            and self.staging_finished()
        )

    def reset_finalization(self) -> None:
        self.finalized_result_id = None
        self.finished_without_winner_reason = None

        # Reset final verified page
        self.final_page_verified = False
        self.final_page_url = None
        self.final_page_notes = None
        self.final_page_observation_id = None
        self.reset_final_page_retry()

        # Reset transaction staging
        self.staging_url = None
        self.staging_type = None
        self.staging_notes = None

        if self.requires_staging:
            self.staging_status = StagingStatus.PENDING
        else:
            self.staging_status = StagingStatus.NOT_REQUIRED
