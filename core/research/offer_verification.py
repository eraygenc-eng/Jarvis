"""Browser evidence and quote validation, independent of research category/site."""

import re
from typing import Literal
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field

from core.research.comparison_state import ComparisonResult, ComparisonState, VerificationStatus
from core.research.evidence import BrowserObservation, get_snapshot_subtree
from core.research.ranking import get_public_total, get_conditional_total, normalize_currency
from core.research.research_utils import get_product_identity_conflict, normalize_identity, normalize_price_condition, url_belongs_to_source
from core.research.verification import is_domain_url, urls_match, validate_observed_amount


class OfferQuote(BaseModel):
    """Fresh quote for ONE offer. All evidence is copied from its snapshot subtree.

    offer_ref identifies the smallest container holding that offer, excluding other
    offers where possible. price_evidence must include the price node's [ref=...].
    price_scope='total' means the full requested quantity, passengers, stay or rental;
    scope_evidence must show that scope. Unit/night/day/from prices stay provisional.
    fees_included requires explicit evidence that ALL mandatory costs are included.
    Otherwise mandatory_fees is the known sum of other mandatory costs, with evidence.
    Product delivery can use shipping_cost. Do not invent zero fees for travel.
    regular_price means a current public payable price, never a crossed-out list price.
    Conditional prices require price_condition and its copied condition_evidence.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    offer_ref: str
    identity_evidence: str
    seller: str
    seller_evidence: str
    currency: str
    price_evidence: str
    price_amount_texts: dict[str, str]
    price_decimal_separator: Literal[".", ","]
    price: float | None = Field(default=None, ge=0)
    regular_price: float | None = Field(default=None, ge=0)
    currency_evidence: str | None = None
    price_condition: str | None = None
    condition_evidence: str | None = None
    price_scope: Literal["total", "unit", "unknown"] = "unknown"
    scope_evidence: str | None = None
    fees_included: bool = False
    mandatory_fees: float | None = Field(default=None, ge=0)
    fees_evidence: str | None = None
    fee_amount_text: str | None = None
    shipping_cost: float | None = Field(default=None, ge=0)
    shipping_evidence: str | None = None
    shipping_amount_text: str | None = None
    variant: str | None = None
    sku: str | None = None
    notes: str | None = None


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _find_scope_line(
    scope: str,
    fragment: str,
) -> str | None:
    fragment = _clean_text(fragment)

    if not fragment:
        return None

    for raw_line in scope.splitlines():
        line = _clean_text(raw_line)

        if fragment.casefold() in line.casefold():
            return line

    return None


def _excerpt(
    scope: str,
    value: str | None,
    label: str,
) -> str:
    cleaned = _clean_text(value)

    if not cleaned:
        raise ValueError(
            f"{label} is required."
        )

    normalized_scope = _clean_text(scope)

    # Best case: exact copied evidence.
    if cleaned.casefold() in normalized_scope.casefold():
        return cleaned

    candidates = []

    # Try quoted text from a descriptive LLM sentence.
    candidates.extend(
        re.findall(
            r'''["'“”‘’]([^"'“”‘’]{4,})["'“”‘’]''',
            cleaned,
        )
    )

    # Also support descriptions such as:
    # "Product title: Logitech ..."
    for part in re.split(r"[;\n]", cleaned):
        if ":" not in part:
            continue

        candidate = part.split(":", 1)[1].strip(" .")

        if len(candidate) >= 4:
            candidates.append(candidate)

    # Prefer the most specific fragment.
    for candidate in sorted(
        set(candidates),
        key=len,
        reverse=True,
    ):
        matched_line = _find_scope_line(
            scope,
            candidate,
        )

        if matched_line:
            return matched_line

    raise ValueError(
        f"{label} could not be grounded "
        "in the selected offer subtree."
    )


def _amount(excerpt, text, value, separator, label):
    error = validate_observed_amount(excerpt, text or "", value, separator)
    if error:
        raise ValueError(f"{label}: {error}")

def _is_generic_seller(value: str | None) -> bool:
    normalized = normalize_identity(value or "")

    if not normalized:
        return True

    generic_markers = (
        "marketplace",
        "listedsellers",
        "listedseller",
        "unknown",
        "sellerunknown",
    )

    return any(
        marker in normalized
        for marker in generic_markers
    )


def _currency_token_present(
    text: str,
    token: str,
) -> bool:
    if token.isalnum():
        return (
            re.search(
                r"(?<!\w)"
                + re.escape(token)
                + r"(?!\w)",
                text,
                re.I,
            )
            is not None
        )

    return token in text


def validate_quote(state: ComparisonState, result: ComparisonResult,
                   observation: BrowserObservation, quote: OfferQuote) -> str:
    if not result.offer_url:
        raise ValueError("Store the exact seller/provider offer URL with research_set_offer_url first.")
    if not urls_match(result.offer_url, observation.page_url):
        raise ValueError("The current browser page does not match the exact offer URL.")
    if not url_belongs_to_source(result.source, observation.page_url):
        raise ValueError("The verification page does not belong to this direct source.")
    if is_domain_url(observation.page_url, "akakce.com"):
        raise ValueError("Open the actual merchant page; Akakce is a discovery source.")

    scope = get_snapshot_subtree(observation.page_text, quote.offer_ref)
    identity = _excerpt(scope, quote.identity_evidence, "Identity evidence")

    seller_evidence = _excerpt(
        scope,
        quote.seller_evidence,
        "Seller/provider evidence",
    )

    seller = quote.seller.strip()

    if not seller:
        raise ValueError(
            "Seller/provider is required."
        )

    if (
        normalize_identity(seller)
        not in normalize_identity(scope)
    ):
        raise ValueError(
            "Seller/provider could not be found "
            "in the selected offer subtree."
        )

    if (
        result.seller
        and not _is_generic_seller(result.seller)
        and normalize_identity(result.seller)
        != normalize_identity(seller)
    ):
        raise ValueError(
            "seller/provider changed. "
            "Store it as a separate offer."
        )

    if state.target_product:
        conflict = get_product_identity_conflict(state.target_product, identity)
        if conflict:
            raise ValueError(f"Product identity mismatch: {conflict}")

    for field in ("sku", "variant"):
        observed = getattr(quote, field)
        expected = getattr(result, field)

        if (
            observed
            and normalize_identity(observed)
            not in normalize_identity(scope)
        ):
            raise ValueError(
                f"{field} is not supported "
                "by the identity evidence."
            )

        if (
            expected
            and normalize_identity(expected)
            not in normalize_identity(scope)
        ):
            raise ValueError(
                f"The stored {field} is not supported "
                "by fresh identity evidence."
            )

        if (
            observed
            and expected
            and normalize_identity(observed)
            != normalize_identity(expected)
        ):
            raise ValueError(
                f"The observed {field} does not match "
                f"the stored {field}."
            )

    evidence = _excerpt(scope, quote.price_evidence, "Price evidence")
    if quote.price is None and quote.regular_price is None:
        raise ValueError("Provide a freshly observed price or regular_price.")
    if not re.search(r"\[ref=[^\]]+\]", evidence):
        raise ValueError("Price evidence must include its snapshot node reference.")
    for field in ("price", "regular_price"):
        value = getattr(quote, field)
        if value is None:
            continue
        _amount(evidence, quote.price_amount_texts.get(field), value,
                quote.price_decimal_separator, field)
    # A linked price for another seller/variant is not the current page's quote.
    for ref in re.findall(r"\[ref=([^\]]+)\]", evidence):
        node = get_snapshot_subtree(scope, ref)
        for target in re.findall(r"(?m)^\s+- /url: (.+)$", node):
            target = target.strip().strip("\"'")
            if not urls_match(observation.page_url, urljoin(observation.page_url, target)):
                raise ValueError("The price evidence links to a different offer.")

    currency = normalize_currency(quote.currency)
    if currency is None:
        raise ValueError("An explicit three-letter currency code is required.")
    currency_text = _excerpt(scope, quote.currency_evidence or quote.price_evidence, "Currency evidence")
    aliases = {"TRY": ("TRY", "TL", "₺"), "EUR": ("EUR", "€"), "GBP": ("GBP", "£")}
    if not any(
        _currency_token_present(
            currency_text,
            token,
        )
        for token in aliases.get(
            currency,
            (currency,),
        )
    ):
        raise ValueError("Currency is not explicit in its evidence; ambiguous symbols alone are insufficient.")
    if normalize_price_condition(quote.price_condition):
        _excerpt(scope, quote.condition_evidence, "Price condition evidence")
    if (
        quote.price_scope == "total"
        and state.category not in {"product", "general"}
    ):
        _excerpt(scope, quote.scope_evidence, "Full request scope evidence")
    if quote.fees_included:
        _excerpt(scope, quote.fees_evidence, "All mandatory costs included evidence")
        if quote.shipping_cost is not None or quote.mandatory_fees is not None:
            raise ValueError("An inclusive total cannot also add shipping or mandatory fees.")
    elif quote.mandatory_fees is not None:
        fee_evidence = _excerpt(scope, quote.fees_evidence, "Mandatory fee evidence")
        _amount(fee_evidence, quote.fee_amount_text, quote.mandatory_fees,
                quote.price_decimal_separator, "mandatory_fees")
    if quote.shipping_cost is not None:
        if state.category not in {"product", "general"}:
            raise ValueError("Use mandatory_fees or an inclusive total for travel, not shipping_cost.")
        shipping = _excerpt(scope, quote.shipping_evidence, "Shipping evidence")

        free_shipping_labels = {
            "kargo bedava",
            "ücretsiz kargo",
            "bedava kargo",
            "free shipping",
            "free delivery",
        }

        normalized_shipping = shipping.casefold()

        if quote.shipping_amount_text:
            _amount(
                shipping,
                quote.shipping_amount_text,
                quote.shipping_cost,
                quote.price_decimal_separator,
                "shipping_cost",
            )
        elif (
            quote.shipping_cost != 0
            or not any(
                label in normalized_shipping
                for label in free_shipping_labels
            )
        ):
            raise ValueError(
                "Shipping requires a numeric amount "
                "or an explicit free-shipping label."
            )
    return scope


def quote_prices(result: ComparisonResult) -> dict:
    return {
        "price": result.price, "regular_price": result.regular_price,
        "public_total": get_public_total(result),
        "conditional_total": get_conditional_total(result),
        "currency": result.currency, "seller": result.seller,
        "price_condition": result.price_condition, "price_scope": result.price_scope,
    }


def apply_quote(result: ComparisonResult, observation: BrowserObservation, quote: OfferQuote) -> None:
    if not result.price_history:
        result.price_history.append({"stage": "discovery", "url": result.url, **quote_prices(result)})
    for field in ("price", "regular_price", "shipping_cost", "mandatory_fees",
                  "fees_included", "price_scope", "scope_evidence", "variant", "sku"):
        setattr(result, field, getattr(quote, field))
    result.seller = quote.seller.strip()
    result.currency = normalize_currency(quote.currency)
    result.price_condition = normalize_price_condition(quote.price_condition)
    result.effective_total = result.public_total = result.conditional_total = None
    # Recalculate using ONLY the new quote. Unit prices never become final totals.
    result.public_total = get_public_total(result, strict=True)
    result.conditional_total = get_conditional_total(result, strict=True)
    result.verified = True
    result.verification_status = VerificationStatus.VERIFIED
    result.verification_reason = None
    result.verification_url = observation.page_url
    result.verification_observation_id = observation.observation_id
    result.verification_price_evidence = quote.price_evidence
    result.verification_offer_ref = quote.offer_ref
    result.verification_identity_evidence = quote.identity_evidence
    result.verification_seller_evidence = quote.seller_evidence
    result.verification_notes = quote.notes
    result.verified_details = {"quote": quote.model_dump()}
    result.price_history.append({
        "stage": "verified", "url": observation.page_url,
        "captured_at": observation.captured_at.isoformat(),
        "observation_id": observation.observation_id, **quote_prices(result),
    })
