from core.research.research_controller import ResearchController
from core.research.research_state import ResearchState


def test_controller_checks_url_without_registering_it():
    state = ResearchState(query="test")
    controller = ResearchController(state)

    url = "https://example.com/product?id=5&utm_source=google"

    # Checking the URL should not store it
    result = controller.has_visited_url(url)

    assert result is False
    assert state.visited_urls == set()


def test_controller_detects_registered_url():
    state = ResearchState(query="test")
    controller = ResearchController(state)

    controller.register_url(
        "https://example.com/product?id=5&utm_source=google"
    )

    result = controller.has_visited_url(
        "https://example.com/product?id=5&utm_source=instagram"
    )

    assert result is True


def test_controller_tracks_navigation_attempts():
    state = ResearchState(query="test")
    controller = ResearchController(state)

    url = "https://example.com/product?id=5"

    # URL was not attempted yet
    assert controller.has_attempted_url(url) is False

    # First attempt should be registered
    assert controller.register_navigation_attempt(url) is True

    # Now the same URL should be detected
    assert controller.has_attempted_url(url) is True


def test_controller_blocks_tracking_variant_in_same_turn():
    state = ResearchState(query="test")
    controller = ResearchController(state)

    first_url = (
        "https://example.com/product?id=5&utm_source=google"
    )

    second_url = (
        "https://example.com/product?id=5&utm_source=instagram"
    )

    assert controller.register_navigation_attempt(first_url) is True

    # Same page with different tracking should count as duplicate
    assert controller.has_attempted_url(second_url) is True
    assert controller.register_navigation_attempt(second_url) is False


def test_controller_reset_navigation_attempts():
    state = ResearchState(query="test")
    controller = ResearchController(state)

    url = "https://example.com/product?id=5"

    controller.register_navigation_attempt(url)

    assert controller.has_attempted_url(url) is True

    # Simulate starting a new agent turn
    controller.reset_navigation_attempts()

    assert controller.has_attempted_url(url) is False

    # The same URL can be attempted again in the new turn
    assert controller.register_navigation_attempt(url) is True