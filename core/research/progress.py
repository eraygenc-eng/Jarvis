import json
from typing import Any

from core.research.comparison_state import ComparisonState
from core.research.ranking import get_public_total


MAX_PENDING_RESULTS = 3


def _enum_value(value: Any) -> Any:
    """Return the plain value of an enum when possible."""
    return getattr(value, "value", value)


def _build_source_progress(
    state: ComparisonState,
) -> list[dict[str, Any]]:
    """Build a compact summary for every planned source."""

    sources = []

    for source in state.planned_sources:
        source_state = state.get_source_state(source)

        if source_state is None:
            continue

        sources.append(
            {
                "source": source,
                "status": _enum_value(source_state.status),
                "results": len(source_state.result_ids),
                "discovery_attempts": (
                    source_state.discovery_attempt_count()
                ),
            }
        )

    return sources


def _get_pending_results(
    state: ComparisonState,
) -> list:
    """Return offers that still need exact-page verification."""

    return [
        result
        for result in state.results
        if _enum_value(result.verification_status) == "pending"
    ]


def _build_pending_progress(
    state: ComparisonState,
) -> dict[str, Any]:
    """Expose only a few pending offers to keep context small."""

    pending = _get_pending_results(state)

    visible = []

    for result in pending[:MAX_PENDING_RESULTS]:
        visible.append(
            {
                "result_id": result.result_id,
                "source": result.source,
                "seller": result.seller,
                "model": result.model,
                "variant": result.variant,
                "sku": result.sku,
                "offer_url": result.offer_url,
            }
        )

    return {
        "count": len(pending),
        "items": visible,
    }


def _build_best_verified_public(
    state: ComparisonState,
) -> list[dict[str, Any]]:
    """
    Return the cheapest verified public offer per currency.

    Different currencies are never compared with each other.
    """

    best_by_currency: dict[str, tuple[Any, float]] = {}

    for result in state.results:
        if not result.verified:
            continue

        currency = result.currency

        if not currency:
            continue

        total = get_public_total(
            result,
            strict=True,
        )

        if total is None:
            continue

        current = best_by_currency.get(currency)

        if current is None or total < current[1]:
            best_by_currency[currency] = (
                result,
                total,
            )

    output = []

    for currency, (result, total) in best_by_currency.items():
        output.append(
            {
                "currency": currency,
                "result_id": result.result_id,
                "source": result.source,
                "seller": result.seller,
                "total": total,
                "offer_url": result.offer_url,
            }
        )

    return output


def _build_finalized_result(
    state: ComparisonState,
) -> dict[str, Any] | None:
    """Return compact information about the selected winner."""

    result_id = state.finalized_result_id

    if result_id is None:
        return None

    result = state.get_result(result_id)

    if result is None:
        return {
            "result_id": result_id,
        }

    return {
        "result_id": result.result_id,
        "source": result.source,
        "seller": result.seller,
        "offer_url": result.offer_url,
        "currency": result.currency,
        "public_total": get_public_total(
            result,
            strict=True,
        ),
    }


def _build_next_action(
    state: ComparisonState,
) -> dict[str, Any]:
    """
    Decide the next research phase from durable Python state.

    This prevents the model from reconstructing progress from
    old browser messages.
    """

    if state.is_ready_to_return():
        return {
            "action": "ready_for_report",
        }

    # Finish sources already in progress before starting new ones.
    for source in state.planned_sources:
        source_state = state.get_source_state(source)

        if source_state is None:
            continue

        if _enum_value(source_state.status) == "researching":
            return {
                "action": "continue_source",
                "source": source,
            }

    # Start the next untouched source.
    for source in state.planned_sources:
        source_state = state.get_source_state(source)

        if source_state is None:
            continue

        if _enum_value(source_state.status) == "pending":
            return {
                "action": "start_source",
                "source": source,
            }

    # Source discovery is complete. Resolve pending verification.
    pending = _get_pending_results(state)

    if pending:
        result = pending[0]

        return {
            "action": "verify_result",
            "result_id": result.result_id,
            "source": result.source,
            "seller": result.seller,
            "offer_url": result.offer_url,
        }

    # No pending verification remains. Select a winner or finish
    # explicitly without one.
    if not state.is_finalized():
        return {
            "action": "resolve_final_decision",
        }

    # Winner exists but the browser must still be confirmed on it.
    if not state.final_page_verified:
        finalized = _build_finalized_result(state)

        return {
            "action": "verify_final_page",
            "result": finalized,
        }

    # Continue transaction staging only when required.
    if not state.staging_finished():
        return {
            "action": "continue_staging",
            "status": _enum_value(state.staging_status),
        }

    return {
        "action": "ready_for_report",
    }


def build_research_progress(
    state: ComparisonState,
) -> dict[str, Any]:
    """Build the compact model-facing research state."""

    return {
        "category": getattr(
            state,
            "category",
            None,
        ),
        "original_request": state.query,
        "target_product": getattr(
            state,
            "target_product",
            None,
        ),
        "criteria": state.criteria,
        "sources": _build_source_progress(state),
        "pending_verifications": _build_pending_progress(
            state
        ),
        "best_verified_public_by_currency": (
            _build_best_verified_public(state)
        ),
        "finalized_result": _build_finalized_result(state),
        "final_page_verified": state.final_page_verified,
        "staging": {
            "required": state.requires_staging,
            "status": _enum_value(state.staging_status),
        },
        "ready_to_return": state.is_ready_to_return(),
        "next_action": _build_next_action(state),
    }


def render_research_progress(
    state: ComparisonState,
) -> str:
    """Serialize research progress as compact JSON."""

    return json.dumps(
        build_research_progress(state),
        ensure_ascii=False,
        separators=(",", ":"),
    )