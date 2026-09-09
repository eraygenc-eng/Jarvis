from core.research.comparison_state import (
    ComparisonResult,
    ComparisonState,
)


def get_public_total(
    result: ComparisonResult,
    strict: bool = False,
) -> float | None:
    # Prefer an explicitly known public total
    if result.public_total is not None:
        return result.public_total

    # effective_total is public when no condition exists
    if (
        result.price_condition is None
        and result.effective_total is not None
    ):
        return result.effective_total

    base_price = result.regular_price

    if (
        base_price is None
        and result.price_condition is None
    ):
        base_price = result.price

    if base_price is None:
        return None

    # Include known shipping
    if result.shipping_cost is not None:
        return base_price + result.shipping_cost

    # Final ranking should not assume unknown shipping is zero
    if strict:
        return None

    # Provisional research ranking may use visible price
    return base_price


def get_conditional_total(
    result: ComparisonResult,
    strict: bool = False,
) -> float | None:
    # Conditional price must have a requirement
    if not result.price_condition:
        return None

    if result.conditional_total is not None:
        return result.conditional_total

    if result.effective_total is not None:
        return result.effective_total

    if result.price is None:
        return None

    if result.shipping_cost is not None:
        return result.price + result.shipping_cost

    if strict:
        return None

    return result.price


def get_best_known_total(
    result: ComparisonResult,
    strict: bool = False,
) -> float | None:
    totals = [
        total
        for total in (
            get_public_total(result, strict),
            get_conditional_total(result, strict),
        )
        if total is not None
    ]

    if not totals:
        return None

    return min(totals)


def _get_candidates(
    state: ComparisonState,
    verified_only: bool,
) -> list[ComparisonResult]:
    if verified_only:
        return state.get_verified_results()

    return state.results


def find_best_public(
    state: ComparisonState,
    verified_only: bool = False,
    strict: bool = False,
) -> ComparisonResult | None:
    candidates = _get_candidates(
        state,
        verified_only,
    )

    candidates = [
        result
        for result in candidates
        if get_public_total(result, strict)
        is not None
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda result: get_public_total(
            result,
            strict,
        ),
    )


def find_best_conditional(
    state: ComparisonState,
    verified_only: bool = False,
    strict: bool = False,
) -> ComparisonResult | None:
    candidates = _get_candidates(
        state,
        verified_only,
    )

    candidates = [
        result
        for result in candidates
        if get_conditional_total(
            result,
            strict,
        )
        is not None
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda result: get_conditional_total(
            result,
            strict,
        ),
    )


def find_best_overall(
    state: ComparisonState,
    verified_only: bool = False,
    strict: bool = False,
) -> ComparisonResult | None:
    candidates = _get_candidates(
        state,
        verified_only,
    )

    candidates = [
        result
        for result in candidates
        if get_best_known_total(
            result,
            strict,
        )
        is not None
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda result: get_best_known_total(
            result,
            strict,
        ),
    )


def refresh_source_rankings(
    state: ComparisonState,
    source: str,
) -> None:
    source_state = state.get_source_state(source)

    if source_state is None:
        return

    source_results = state.get_results_for_source(
        source
    )

    public_candidates = [
        result
        for result in source_results
        if get_public_total(result) is not None
    ]

    conditional_candidates = [
        result
        for result in source_results
        if get_conditional_total(result) is not None
    ]

    if public_candidates:
        best_public = min(
            public_candidates,
            key=get_public_total,
        )

        source_state.best_public_result_id = (
            best_public.result_id
        )
    else:
        source_state.best_public_result_id = None

    if conditional_candidates:
        best_conditional = min(
            conditional_candidates,
            key=get_conditional_total,
        )

        source_state.best_conditional_result_id = (
            best_conditional.result_id
        )
    else:
        source_state.best_conditional_result_id = None


def find_best_public_for_source(
    state: ComparisonState,
    source: str,
    verified_only: bool = False,
    strict: bool = False,
) -> ComparisonResult | None:
    # Get results collected only from this source
    candidates = state.get_results_for_source(source)

    if verified_only:
        candidates = [
            result
            for result in candidates
            if result.verified
        ]

    candidates = [
        result
        for result in candidates
        if get_public_total(
            result,
            strict,
        ) is not None
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda result: get_public_total(
            result,
            strict,
        ),
    )


def find_best_conditional_for_source(
    state: ComparisonState,
    source: str,
    verified_only: bool = False,
    strict: bool = False,
) -> ComparisonResult | None:
    # Get results collected only from this source
    candidates = state.get_results_for_source(source)

    if verified_only:
        candidates = [
            result
            for result in candidates
            if result.verified
        ]

    candidates = [
        result
        for result in candidates
        if get_conditional_total(
            result,
            strict,
        ) is not None
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda result: get_conditional_total(
            result,
            strict,
        ),
    )


def get_unverified_source_winners(
    state: ComparisonState,
    source: str,
) -> list[ComparisonResult]:
    """
    Return current source winners that still need exact-page verification.
    """

    winners = []

    best_public = find_best_public_for_source(
        state,
        source,
    )

    best_conditional = find_best_conditional_for_source(
        state,
        source,
    )

    # Public winner must be verified
    if (
        best_public is not None
        and not best_public.verified
    ):
        winners.append(best_public)

    # Conditional winner must also be verified when it is a different offer
    if (
        best_conditional is not None
        and not best_conditional.verified
        and best_conditional.result_id
        not in {
            result.result_id
            for result in winners
        }
    ):
        winners.append(best_conditional)

    return winners