from core.research.research_state import ResearchState


def test_register_url_rejects_duplicate():
    state = ResearchState(query="test research")

    # First visit should be accepted
    first_result = state.register_url(
        "https://example.com/product"
    )

    # Same URL should be rejected
    second_result = state.register_url(
        "https://example.com/product"
    )

    assert first_result is True
    assert second_result is False
    assert len(state.visited_urls) == 1


def test_register_source_rejects_duplicate():
    state = ResearchState(query="test research")

    # First source should be accepted
    first_result = state.register_source("Example.com")

    # Same source with different case should be rejected
    second_result = state.register_source("example.com")

    assert first_result is True
    assert second_result is False
    assert len(state.visited_sources) == 1


def test_step_limit_stops_research():
    state = ResearchState(
        query="test research",
        max_steps=2,
    )

    assert state.record_step() is True
    assert state.record_step() is True

    # Third step should be blocked
    assert state.record_step() is False

    assert state.should_stop() is True
    assert state.finish_reason == "max_steps_reached"


def test_no_progress_stops_research():
    state = ResearchState(
        query="test research",
        max_no_progress=2,
    )

    state.record_no_progress()
    assert state.should_stop() is False

    state.record_no_progress()

    assert state.should_stop() is True
    assert state.finish_reason == "no_progress"


def test_progress_resets_no_progress_counter():
    state = ResearchState(query="test research")

    state.record_no_progress()
    state.record_no_progress()

    assert state.no_progress_count == 2

    # Useful progress should reset the counter
    state.record_progress()

    assert state.no_progress_count == 0