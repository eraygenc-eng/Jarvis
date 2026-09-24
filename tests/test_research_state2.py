from core.research.research_state import ResearchState, normalize_url


def test_normalize_url_removes_utm_parameters():
    # UTM parameters should not change URL identity
    url = (
        "https://example.com/product"
        "?id=5&utm_source=google&utm_campaign=sale&color=black"
    )

    result = normalize_url(url)

    assert result == (
        "https://example.com/product?id=5&color=black"
    )


def test_normalize_url_removes_known_tracking_parameters():
    # Known tracking parameters should also be removed
    url = (
        "https://example.com/product"
        "?id=5&fbclid=12345&gclid=abc"
    )

    result = normalize_url(url)

    assert result == "https://example.com/product?id=5"


def test_normalize_url_normalizes_scheme_and_domain():
    # Scheme and domain should use lowercase
    url = "HTTPS://Example.COM/product?id=5"

    result = normalize_url(url)

    assert result == "https://example.com/product?id=5"


def test_register_url_blocks_tracking_variant():
    state = ResearchState(query="test")

    # First visit should be accepted
    first_result = state.register_url(
        "https://example.com/product?id=5&utm_source=google"
    )

    # Same page with different tracking should be rejected
    second_result = state.register_url(
        "https://example.com/product?id=5&utm_source=instagram"
    )

    assert first_result is True
    assert second_result is False


def test_register_url_allows_different_page():
    state = ResearchState(query="test")

    first_result = state.register_url(
        "https://example.com/product?id=5"
    )

    second_result = state.register_url(
        "https://example.com/product?id=6"
    )

    assert first_result is True
    assert second_result is True


def test_register_url_stores_normalized_url():
    state = ResearchState(query="test")

    state.register_url(
        "HTTPS://Example.COM/product?id=5&utm_source=google"
    )

    assert state.visited_urls == {
        "https://example.com/product?id=5"
    }