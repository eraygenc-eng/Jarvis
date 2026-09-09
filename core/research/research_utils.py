from core.research.task_classifier import contains_keyword


PRICE_FOCUSED_KEYWORDS = [
    "en ucuz",
    "en uygun fiyat",
    "en düşük fiyat",
    "cheapest",
    "lowest price",
    "most affordable",
]


def normalize_identity(value: str) -> str:
    # Normalize identifiers for reliable comparison
    return "".join(
        character
        for character in value.casefold().strip()
        if character.isalnum()
    )


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