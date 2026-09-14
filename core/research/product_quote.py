"""Small model input: select refs; Python copies and parses the evidence."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from core.research.offer_verification import OfferQuote
from core.research.quote_evidence import SnapshotIndex, contains, visible_text


class ProductQuoteSelection(BaseModel):
    """Select current product-page refs, not descriptions or invented amounts.

    offer_ref contains title, actual seller, current price and delivery evidence.
    price_ref must be the payable price, not installments, list price or another
    seller. amount_text is optional and numeric only when the node is ambiguous.
    A quantity_ref must show the selected quantity; omit it to keep a unit quote.
    shipping_ref must describe delivery for THIS offer. Unknown shipping stays null.
    Use condition_ref for membership/coupon prices. No automatic eligibility.
    """
    model_config = ConfigDict(extra="forbid")
    offer_ref: str
    identity_ref: str
    seller_ref: str
    seller: str
    price_ref: str
    currency: str
    decimal_separator: Literal[".", ","]
    amount_text: str | None = None
    currency_ref: str | None = None
    quantity_ref: str | None = None
    shipping_ref: str | None = None
    shipping_amount_text: str | None = None
    condition_ref: str | None = None
    variant: str | None = None
    sku: str | None = None


def read_amount(text: str, separator: str, selected: str | None = None) -> tuple[str, float]:
    from core.research.verification import validate_observed_amount
    group = "," if separator == "." else "."
    pattern = rf"(?<![\w.,])\d+(?:{re.escape(group)}\d{{3}})*(?:{re.escape(separator)}\d{{1,2}})?(?![\w.,])"
    candidates = list(dict.fromkeys(re.findall(pattern, visible_text(text))))
    token = selected.strip() if selected else candidates[0] if len(candidates) == 1 else ""
    if not token:
        raise ValueError("Select one price node; ambiguous amounts require numeric amount_text and the correct decimal_separator.")
    try:
        value = float(Decimal(token.replace(group, "").replace(separator, ".")))
    except Exception as error:
        raise ValueError("amount_text must contain only the numeric amount, without currency.") from error
    error = validate_observed_amount(visible_text(text), token, value, separator)
    if error:
        raise ValueError(error)
    return token, value


def build_product_quote(state, observation, selection: ProductQuoteSelection) -> OfferQuote:
    if state.category != "product":
        raise ValueError("Reference-based product verification requires a product research state.")
    page = SnapshotIndex(observation.page_text)
    scope_node = page.node(selection.offer_ref)
    selected_nodes = [page.node(ref) for name, ref in selection.model_dump().items()
                      if name.endswith("_ref") and ref and name != "offer_ref"]
    outside = [node for node in selected_nodes if not contains(scope_node, node)]
    if outside:
        common = selected_nodes[0]
        while common and not all(contains(common, node) for node in selected_nodes):
            common = common.parent
        common_ref = next((ref for ref, node in page.refs.items() if node is common), None)
        hint = f" Common container: {common_ref}." if common_ref else ""
        raise ValueError(
            "Selected evidence exists on this snapshot but is outside offer_ref "
            f"{selection.offer_ref}.{hint} Choose a container that includes your refs, "
            "then ensure they all describe the same offer. Repeating browser_snapshot "
            "with the same selection will not fix the scope."
        )
    index = SnapshotIndex(page.text(scope_node))
    identity = index.read(selection.identity_ref)
    seller = index.read(selection.seller_ref)
    price = index.read(selection.price_ref)
    if re.search(r"\b(deletion|strikethrough|installment|taksit|eski fiyat|list price)\b", price, re.I):
        raise ValueError("Select the current payable price, not an installment or previous/list price.")
    token, amount = read_amount(price, selection.decimal_separator, selection.amount_text)
    quantity_evidence = index.read(selection.quantity_ref) if selection.quantity_ref else None
    quantity = None
    if quantity_evidence:
        numbers = re.findall(r"\b\d+\b", visible_text(quantity_evidence))
        if len(numbers) == 1:
            quantity = int(numbers[0])
    requested = state.criteria.get("quantity", 1)
    if quantity_evidence and quantity != requested:
        raise ValueError(f"Selected quantity does not match requested quantity {requested}.")
    # A product unit price cannot silently become a multi-item order total.
    scope = "total" if quantity == requested == 1 else "unit"
    shipping_evidence = index.read(selection.shipping_ref) if selection.shipping_ref else None
    shipping = shipping_token = None
    if shipping_evidence:
        text = visible_text(shipping_evidence).casefold()
        if re.search(r"ücretsiz kargo|kargo bedava|bedava kargo|free (?:shipping|delivery)", text) and not re.search(r"altı|üzeri|over|minimum|üyel|member", text):
            shipping = 0.0
        else:
            shipping_token, shipping = read_amount(shipping_evidence, selection.decimal_separator, selection.shipping_amount_text)
    condition = index.read(selection.condition_ref) if selection.condition_ref else None
    return OfferQuote(
        offer_ref=selection.offer_ref, identity_evidence=identity,
        seller=selection.seller, seller_evidence=seller, currency=selection.currency,
        currency_evidence=index.read(selection.currency_ref) if selection.currency_ref else price,
        price_evidence=price, price_amount_texts={"price": token},
        price_decimal_separator=selection.decimal_separator, price=amount,
        price_scope=scope, scope_evidence=quantity_evidence,
        shipping_cost=shipping, shipping_evidence=shipping_evidence,
        shipping_amount_text=shipping_token,
        price_condition=visible_text(condition) if condition else None,
        condition_evidence=condition, variant=selection.variant, sku=selection.sku,
    )
