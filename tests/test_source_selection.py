from core.research.source_planner import select_sources


DEFAULT_SOURCES = [
    "Google Shopping",
    "Trendyol",
    "Hepsiburada",
    "Akakce",
    "Ciceksepeti",
]


def test_uses_all_default_sources_when_user_does_not_specify_any():
    # No source preference means use all default sources
    result = select_sources(
        "En ucuz iPhone'u bul",
        DEFAULT_SOURCES,
    )

    assert result.sources == DEFAULT_SOURCES
    assert result.needs_clarification is False
    assert result.requested_count is None


def test_uses_only_explicit_sources():
    # Use only the sources explicitly named by the user
    result = select_sources(
        "Trendyol, Akakce ve Hepsiburada'ya bak",
        DEFAULT_SOURCES,
    )

    assert result.sources == [
        "Trendyol",
        "Hepsiburada",
        "Akakce",
    ]
    assert result.needs_clarification is False


def test_asks_for_clarification_when_only_count_is_given_turkish():
    # A source count without names requires clarification
    result = select_sources(
        "3 siteye bak",
        DEFAULT_SOURCES,
    )

    assert result.sources == []
    assert result.needs_clarification is True
    assert result.requested_count == 3


def test_asks_for_clarification_when_only_count_is_given_english():
    # English source-count requests should behave the same way
    result = select_sources(
        "Check 3 websites",
        DEFAULT_SOURCES,
    )

    assert result.sources == []
    assert result.needs_clarification is True
    assert result.requested_count == 3


def test_automatically_selects_sources_when_user_allows_it():
    # Jarvis may choose sources when the user explicitly allows it
    result = select_sources(
        "3 siteye bak, fark etmez",
        DEFAULT_SOURCES,
    )

    assert result.sources == [
        "Google Shopping",
        "Trendyol",
        "Hepsiburada",
    ]
    assert result.needs_clarification is False
    assert result.requested_count == 3


def test_automatic_source_choice_works_in_english():
    # English automatic-choice intent should also work
    result = select_sources(
        "Check 3 websites, you choose",
        DEFAULT_SOURCES,
    )

    assert result.sources == [
        "Google Shopping",
        "Trendyol",
        "Hepsiburada",
    ]
    assert result.needs_clarification is False
    assert result.requested_count == 3


def test_completes_missing_sources_when_user_allows_it():
    # Keep named sources and fill the remaining slot
    result = select_sources(
        "Trendyol ve Akakce dahil 3 siteye bak, "
        "ucuncusunu sen sec",
        DEFAULT_SOURCES,
    )

    assert result.sources == [
        "Trendyol",
        "Akakce",
        "Google Shopping",
    ]
    assert result.needs_clarification is False
    assert result.requested_count == 3


def test_conflicting_source_count_requires_clarification():
    # Do not guess when source names conflict with the requested count
    result = select_sources(
        "2 siteye bak: Trendyol, Akakce ve Hepsiburada",
        DEFAULT_SOURCES,
    )

    assert result.needs_clarification is True
    assert result.requested_count == 2