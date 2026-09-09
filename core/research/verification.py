from urllib.parse import parse_qsl, unquote, urlparse


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

    for key in shared_keys:
        if expected_identity[key] != current_identity[key]:
            return False

    # Normal case: same merchant and same product path.
    if expected_path == current_path:
        return True

    # Some websites change the slug or canonical path
    # after navigation. Allow this only when there is
    # a strong matching identity parameter.
    if shared_keys:
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

        if value < 0:
            return (
                f"{name} cannot be negative."
            )

    return None