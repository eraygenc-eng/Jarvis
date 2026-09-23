from core.research.research_controller import ResearchController
from core.research.research_state import ResearchState


def test_controller_starts_research_steps():
    state = ResearchState(
        query="test research",
        max_steps=2,
    )
    controller = ResearchController(state)

    # First two steps should be accepted
    assert controller.start_step() is True
    assert controller.start_step() is True

    # Research should stop after the limit
    assert controller.should_stop() is True
    assert state.finish_reason == "max_steps_reached"


def test_controller_rejects_duplicate_url():
    state = ResearchState(query="test research")
    controller = ResearchController(state)

    # First URL should be accepted
    assert controller.register_url(
        "https://example.com/product"
    ) is True

    # Same URL should be rejected
    assert controller.register_url(
        "https://example.com/product"
    ) is False

    assert len(state.visited_urls) == 1


def test_controller_respects_site_limit():
    state = ResearchState(
        query="test research",
        max_sites=2,
    )
    controller = ResearchController(state)

    assert controller.register_source("site1.com") is True
    assert controller.register_source("site2.com") is True

    # Third source should be rejected
    assert controller.register_source("site3.com") is False

    assert len(state.visited_sources) == 2


def test_controller_stops_after_no_progress():
    state = ResearchState(
        query="test research",
        max_no_progress=2,
    )
    controller = ResearchController(state)

    controller.record_no_progress()
    assert controller.should_stop() is False

    controller.record_no_progress()

    assert controller.should_stop() is True
    assert state.finish_reason == "no_progress"


def test_controller_progress_resets_counter():
    state = ResearchState(query="test research")
    controller = ResearchController(state)

    controller.record_no_progress()
    controller.record_no_progress()

    assert state.no_progress_count == 2

    # Useful progress should reset the counter
    controller.record_progress()

    assert state.no_progress_count == 0


def test_controller_finish_and_status():
    state = ResearchState(query="test research")
    controller = ResearchController(state)

    controller.start_step()
    controller.register_source("example.com")

    controller.finish("enough_information")

    status = controller.get_status()

    assert state.finished is True
    assert state.finish_reason == "enough_information"

    assert status["steps"] == 1
    assert status["sites"] == 1
    assert status["finished"] is True