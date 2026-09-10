"""Price comparison rules shared by every research category."""

from decimal import Decimal
from math import isfinite
import re

from core.research.comparison_state import (
    ComparisonResult, ComparisonState, VerificationStatus,
)


def normalize_currency(value: str | None) -> str | None:
    value = (value or "").strip().upper()
    value = {"TL": "TRY", "₺": "TRY", "€": "EUR", "£": "GBP"}.get(value, value)
    return value if re.fullmatch(r"[A-Z]{3}", value) else None


def _money(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) and value >= 0 else None


def _total(result: ComparisonResult, conditional: bool, strict: bool) -> float | None:
    if conditional and not result.price_condition:
        return None
    if strict and result.price_scope != "total":
        return None
    explicit = result.conditional_total if conditional else result.public_total
    if explicit is not None:
        return _money(explicit)
    if result.effective_total is not None and bool(result.price_condition) == conditional:
        return _money(result.effective_total)

    base = result.price if conditional else result.regular_price
    if not conditional and base is None and not result.price_condition:
        base = result.price
    if _money(base) is None:
        return None
    if result.fees_included:
        return base
    costs = [cost for cost in (result.shipping_cost, result.mandatory_fees) if cost is not None]
    if any(_money(cost) is None for cost in costs):
        return None
    if not costs:
        return None if strict else base
    return float(Decimal(str(base)) + sum((Decimal(str(cost)) for cost in costs), Decimal(0)))


def get_public_total(result: ComparisonResult, strict: bool = False) -> float | None:
    return _total(result, conditional=False, strict=strict)


def get_conditional_total(result: ComparisonResult, strict: bool = False) -> float | None:
    return _total(result, conditional=True, strict=strict)


def get_best_known_total(result: ComparisonResult, strict: bool = False) -> float | None:
    totals = [value for value in (
        get_public_total(result, strict), get_conditional_total(result, strict)
    ) if value is not None]
    return min(totals) if totals else None


def _candidates(state, verified_only, source=None, include_blocked=False):
    results = state.results if source is None else state.get_results_for_source(source)
    return [result for result in results
            if result.verification_status != VerificationStatus.REJECTED
            and (include_blocked or result.verification_status != VerificationStatus.BLOCKED)
            and (not verified_only or (
                result.verified and result.verification_status == VerificationStatus.VERIFIED
            ))]


def _best(candidates, total, strict, currency=None):
    candidates = [result for result in candidates if total(result, strict) is not None]
    if currency is not None:
        normalized = normalize_currency(currency)
        if normalized is None:
            return None
        candidates = [result for result in candidates if normalize_currency(result.currency) == normalized]
    currencies = {normalize_currency(result.currency) for result in candidates}
    # Never compare raw numbers across currencies or silently drop unknown currencies.
    if not candidates or None in currencies or len(currencies) != 1:
        return None
    return min(candidates, key=lambda result: total(result, strict))


def find_best_public(state, verified_only=False, strict=None, *, currency=None):
    return _best(_candidates(state, verified_only), get_public_total,
                 verified_only if strict is None else strict, currency)


def find_best_conditional(state, verified_only=False, strict=None, *, currency=None):
    return _best(_candidates(state, verified_only), get_conditional_total,
                 verified_only if strict is None else strict, currency)


def find_best_overall(state, verified_only=False, strict=None, *, currency=None):
    # Conditional prices remain separate until user eligibility is established.
    return find_best_public(state, verified_only, strict, currency=currency)


def find_best_public_for_source(state, source, verified_only=False, strict=None, *, currency=None):
    return _best(_candidates(state, verified_only, source, include_blocked=not verified_only),
                 get_public_total, verified_only if strict is None else strict, currency)


def find_best_conditional_for_source(state, source, verified_only=False, strict=None, *, currency=None):
    return _best(_candidates(state, verified_only, source, include_blocked=not verified_only),
                 get_conditional_total, verified_only if strict is None else strict, currency)


def refresh_source_rankings(state: ComparisonState, source: str) -> None:
    source_state = state.get_source_state(source)
    if source_state is None:
        return
    candidates = _candidates(state, False, source)
    public = _best(candidates, get_public_total, False)
    conditional = _best(candidates, get_conditional_total, False)
    source_state.best_public_result_id = public.result_id if public else None
    source_state.best_conditional_result_id = conditional.result_id if conditional else None


def get_unverified_source_winners(state: ComparisonState, source: str) -> list[ComparisonResult]:
    candidates = _candidates(state, False, source)
    winners = {}
    for currency in {normalize_currency(result.currency) for result in candidates}:
        group = [result for result in candidates if normalize_currency(result.currency) == currency]
        # Unknown currency still needs investigation; it cannot establish a winner.
        for total in (get_public_total, get_conditional_total):
            priced = [result for result in group if total(result) is not None]
            best = min(priced, key=total) if priced else None
            if best and best.verification_status == VerificationStatus.PENDING:
                winners[best.result_id] = best
    return list(winners.values())


def get_pending_verifications(state: ComparisonState) -> list[ComparisonResult]:
    def priority(result):
        total = get_best_known_total(result)
        return (normalize_currency(result.currency) or "", total is None,
                total if total is not None else float("inf"))
    return sorted((result for result in state.results
                   if result.verification_status == VerificationStatus.PENDING), key=priority)


def no_winner_reason(state: ComparisonState) -> str | None:
    if not state.results:
        return "No matching offers were recorded from the planned sources."
    verified = _candidates(state, True)
    if not verified:
        return "No offer could be verified; observed prices remain unconfirmed."
    public = [result for result in verified if get_public_total(result, strict=True) is not None]
    if not public:
        return "No verified public total covers the full request with known mandatory costs. Conditional offers are listed separately."
    currencies = {normalize_currency(result.currency) for result in public}
    if None in currencies or len(currencies) != 1:
        return "Comparable offers use different or unknown currencies. Prices are grouped by currency; no currency conversion was verified."
    return None
