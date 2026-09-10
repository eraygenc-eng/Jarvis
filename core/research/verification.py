import re

from urllib.parse import parse_qsl, unquote, urlparse

from decimal import Decimal, InvalidOperation
from math import isfinite


# Query parameters that can identify a specific product,
# seller, variant, or marketplace offer.
OFFER_IDENTITY_KEYS = {
    "merchantid",
    "merchant_id",
    "sellerid",
    "seller_id",
    "storeid",
    "store_id",
    "magaza",
    "shopid",
    "shop_id",
    "productid",
    "product_id",
    "itemid",
    "item_id",
    "sku",
    "skuid",
    "sku_id",
    "variant",
    "variantid",
    "variant_id",
    "listingid",
    "listing_id",
    "offerid",
    "offer_id",
    "renk",
    "color",
    "size",
    "checkin",
    "checkout",
    "departure",
    "return",
    "adults",
    "children",
    "rooms",
}

# A seller identifies a business, not a specific product or booking.
PRODUCT_IDENTITY_KEYS = {
    "productid", "product_id", "itemid", "item_id", "sku", "skuid",
    "sku_id", "listingid", "listing_id", "offerid", "offer_id",
}


def normalize_host(host: str) -> str:
    # Ignore common www prefix differences
    hostname = host.casefold()

    # Remove port if one exists
    hostname = hostname.split(":", 1)[0]

    return hostname.removeprefix("www.")


def normalize_path(path: str) -> str:
    # Decode escaped URL characters
    normalized = unquote(path or "/")

    # Ignore trailing slash differences
    if normalized != "/":
        normalized = normalized.rstrip("/")

    return normalized


def get_identity_params(url: str) -> dict[str, str]:
    # Read only query parameters that may identify
    # the actual product, seller, or offer.
    parsed = urlparse(url.strip())

    identity = {}

    for key, value in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):
        normalized_key = key.casefold()

        if normalized_key in OFFER_IDENTITY_KEYS:
            identity[normalized_key] = value

    return identity


def urls_match(
    expected_url: str,
    current_url: str,
) -> bool:
    expected = urlparse(expected_url.strip())
    current = urlparse(current_url.strip())

    if (
        expected.scheme not in {"http", "https"}
        or current.scheme not in {"http", "https"}
        or not expected.hostname or not current.hostname
        or expected.username or current.username
    ):
        return False

    expected_host = normalize_host(expected.netloc)
    current_host = normalize_host(current.netloc)

    # Exact offer verification must remain
    # on the same merchant website.
    if expected_host != current_host:
        return False

    expected_path = normalize_path(expected.path)
    current_path = normalize_path(current.path)

    expected_identity = get_identity_params(expected_url)
    current_identity = get_identity_params(current_url)

    # If both URLs expose the same identity key,
    # its value must agree.
    shared_keys = (
        expected_identity.keys()
        & current_identity.keys()
    )

    # Losing a seller, variant or booking parameter is not proof of identity.
    if expected_identity != current_identity:
        return False

    # Normal case: same merchant and same product path.
    if expected_path == current_path:
        return True

    # Some websites change the slug or canonical path
    # after navigation. Allow this only when there is
    # a strong matching identity parameter.
    if shared_keys & PRODUCT_IDENTITY_KEYS:
        return True

    return False


def is_domain_url(
    url: str,
    domain: str,
) -> bool:
    parsed = urlparse(url.strip())

    host = normalize_host(parsed.netloc)
    expected_domain = normalize_host(domain)

    return (
        host == expected_domain
        or host.endswith("." + expected_domain)
    )


def validate_money_values(
    **values,
) -> str | None:
    # Monetary values cannot be negative
    for name, value in values.items():
        if value is None:
            continue

        if not isfinite(value):
            return f"{name} must be finite."

        if value < 0:
            return (
                f"{name} cannot be negative."
            )

    return None



def validate_observed_amount(
    excerpt: str,
    amount_text: str,
    expected_value: float,
    decimal_separator: str,
) -> str | None:
    """Match a numeric amount in an excerpt to the supplied value."""

    if decimal_separator not in {".", ","}:
        return "Decimal separator must be '.' or ','."

    # Ignore spaces used for formatting or digit grouping.
    token = "".join(amount_text.split())
    compact_excerpt = "".join(excerpt.split())

    if not token:
        return "The observed numeric amount is missing."

    group_separator = "," if decimal_separator == "." else "."

    decimal = re.escape(decimal_separator)
    group = re.escape(group_separator)

    # Accept plain digits or correctly grouped thousands.
    number_pattern = (
        rf"(?:[0-9]+|[0-9]{{1,3}}(?:{group}[0-9]{{3}})+)"
        rf"(?:{decimal}[0-9]{{1,2}})?"
    )

    if re.fullmatch(number_pattern, token) is None:
        return "The amount does not match the declared number format."

    # Do not accept a substring of a larger numeric amount.
    occurrence_pattern = (
        rf"(?<![\d.,]){re.escape(token)}(?![\d.,])"
    )

    if re.search(occurrence_pattern, compact_excerpt) is None:
        return "The numeric amount does not occur in the page excerpt."

    normalized = token.replace(group_separator, "")
    normalized = normalized.replace(decimal_separator, ".")

    try:
        observed = Decimal(normalized)
        expected = Decimal(str(expected_value))
    except (InvalidOperation, ValueError):
        return "The amount could not be parsed."

    if not observed.is_finite() or not expected.is_finite():
        return "The amount must be finite."

    if observed != expected:
        return (
            f"Observed amount is {observed}, "
            f"but the supplied value is {expected}."
        )

    return None
