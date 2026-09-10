import re
import unicodedata

from urllib.parse import urlparse

from core.research.task_classifier import contains_keyword


PRICE_FOCUSED_KEYWORDS = [
    "en ucuz",
    "en uygun fiyat",
    "en düşük fiyat",
    "cheapest",
    "lowest price",
    "most affordable",
]


# Direct shopping sources must produce results
# from their own websites.
DIRECT_SOURCE_DOMAINS = {
    "Vatan Computer": {"vatanbilgisayar.com"},
    "Itopya": {"itopya.com"},
    "Hepsiburada": {"hepsiburada.com"},
    "Trendyol": {"trendyol.com"},
    "Ciceksepeti": {"ciceksepeti.com"},
}


# Words that usually identify a materially different
# product edition or generation.
MODEL_SUFFIX_MARKERS = {
    "dex",
    "se",
    "ti",
    "max",
    "ultra",
    "plus",
    "mini",
    "lite",
    "air",
    "xl",
    "pro",
}


# Common request words that are not part
# of the product identity.
IDENTITY_STOPWORDS = {
    "bana",
    "bir",
    "bak",
    "bul",
    "ara",
    "seç",
    "sec",
    "karşılaştır",
    "karsilastir",
    "en",
    "ucuz",
    "ucuzu",
    "uygun",
    "fiyat",
    "fiyatı",
    "fiyati",
    "istiyorum",
    "istiyorum",
    "please",
    "find",
    "search",
    "compare",
    "cheapest",
    "lowest",
    "price",
    "for",
    "me",
}


def normalize_identity(value: str) -> str:
    # Normalize identifiers for reliable comparison
    return "".join(
        character
        for character in value.casefold().strip()
        if character.isalnum()
    )


def normalize_host(host: str) -> str:
    # Normalize website host names.
    normalized = host.casefold()

    # Remove port when present.
    normalized = normalized.split(":", 1)[0]

    return normalized.removeprefix("www.")


def url_belongs_to_source(
    source: str,
    url: str | None,
) -> bool:
    """
    Check whether a result URL belongs to a direct source.

    Aggregators such as Google Shopping and Akakce are handled
    separately and are not restricted here.
    """

    if not url:
        return False

    allowed_domains = DIRECT_SOURCE_DOMAINS.get(source)

    # This guard applies only to known direct sources.
    if allowed_domains is None:
        return True

    parsed = urlparse(url.strip())
    host = normalize_host(parsed.netloc)

    if not host:
        return False

    return any(
        host == domain
        or host.endswith("." + domain)
        for domain in allowed_domains
    )


def identity_tokens(
    value: str,
) -> list[str]:
    # Normalize Unicode text before token comparison.
    normalized = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    # Split letters and numbers separately.
    # RTX5070 -> ["rtx", "5070"]
    # 256GB -> ["256", "gb"]
    tokens = re.findall(
        r"[^\W\d_]+|\d+",
        normalized,
        flags=re.UNICODE,
    )

    return [
        token
        for token in tokens
        if token not in IDENTITY_STOPWORDS
    ]


def get_product_identity_conflict(
    request: str,
    candidate_title: str,
) -> str | None:
    """
    Detect clear product identity mismatches.

    The check is conservative:
    it blocks obvious different models, generations,
    or suffix editions without trying to replace
    exact-page verification.
    """

    request_tokens = identity_tokens(request)
    candidate_tokens = identity_tokens(candidate_title)

    if not request_tokens or not candidate_tokens:
        return None

    request_token_set = set(request_tokens)
    candidate_token_set = set(candidate_tokens)

    # Every important requested identity token
    # should exist in the candidate.
    missing_tokens = (
        request_token_set
        - candidate_token_set
    )

    if missing_tokens:
        return (
            "candidate is missing requested identity token(s): "
            + ", ".join(sorted(missing_tokens))
        )

    # Inspect model/generation numbers.
    numeric_request_tokens = [
        token
        for token in request_tokens
        if token.isdigit()
    ]

    for numeric_token in numeric_request_tokens:
        candidate_positions = [
            index
            for index, token in enumerate(candidate_tokens)
            if token == numeric_token
        ]

        for position in candidate_positions:
            next_position = position + 1

            if next_position >= len(candidate_tokens):
                continue

            next_token = candidate_tokens[next_position]

            # Example:
            # RTX 5070 -> RTX 5070 Ti
            # iPhone 17 -> iPhone 17 Pro
            # Superlight 2 -> Superlight 2 DEX
            if (
                next_token in MODEL_SUFFIX_MARKERS
                and next_token not in request_token_set
            ):
                return (
                    "candidate contains an unrequested "
                    f"model suffix after {numeric_token}: "
                    f"{next_token}"
                )

    return None


def get_canonical_source(
    planned_sources: list[str],
    source: str,
) -> str | None:
    # Match a source against the active research plan
    requested_source = source.strip().casefold()

    return next(
        (
            planned_source
            for planned_source in planned_sources
            if planned_source.casefold() == requested_source
        ),
        None,
    )


def is_price_focused_query(query: str) -> bool:
    # Detect explicit cheapest-price requests
    return any(
        contains_keyword(query, keyword)
        for keyword in PRICE_FOCUSED_KEYWORDS
    )


def normalize_price_condition(
    value: str | None,
) -> str | None:
    """Represent unconditional pricing with None."""

    if value is None:
        return None

    cleaned = " ".join(value.split())

    unconditional_labels = {
        "",
        "public",
        "unconditional",
        "none",
    }

    if cleaned.casefold() in unconditional_labels:
        return None

    return cleaned