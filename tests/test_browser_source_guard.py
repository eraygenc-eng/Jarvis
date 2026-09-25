from core.tools.browser import BrowserManager

from core.research.comparison_state import ComparisonState
from core.research.evidence import ObservationStore
from core.research.research_controller import ResearchController
from core.research.research_state import ResearchState
from core.research.research_tools import create_research_tools


def create_browser_with_controller(
    allowed_domains: set[str],
    dynamic_sources: set[str] | None = None,
) -> tuple[BrowserManager, ResearchController]:
    # Create deterministic research state
    state = ResearchState(
        query="test research",
        allowed_domains=allowed_domains,
        dynamic_sources=dynamic_sources or set(),
    )

    # Control the research rules
    controller = ResearchController(state)

    # Create browser manager without starting Playwright
    browser = BrowserManager()

    # Give browser access to the active controller
    browser.set_research_controller_getter(
        lambda: controller
    )

    return browser, controller


def test_allows_planned_source():
    browser, controller = create_browser_with_controller(
        {"trendyol.com", "akakce.com"}
    )

    result = browser._can_visit_source(
        "https://www.trendyol.com/apple/iphone"
    )

    assert result is True
    assert controller.has_visited_source(
        "trendyol.com"
    )


def test_blocks_source_outside_plan():
    browser, controller = create_browser_with_controller(
        {"trendyol.com", "akakce.com"}
    )

    result = browser._can_visit_source(
        "https://www.amazon.com/iphone"
    )

    assert result is False
    assert not controller.has_visited_source(
        "amazon.com"
    )


def test_allows_second_page_on_same_source():
    browser, controller = create_browser_with_controller(
        {"trendyol.com"}
    )

    first_result = browser._can_visit_source(
        "https://www.trendyol.com/sr?q=iphone"
    )

    second_result = browser._can_visit_source(
        "https://www.trendyol.com/apple/iphone"
    )

    assert first_result is True
    assert second_result is True

    # Both URLs belong to the same source
    assert len(controller.state.visited_sources) == 1


def test_allows_subdomain_of_planned_source():
    browser, _ = create_browser_with_controller(
        {"indeed.com"}
    )

    result = browser._can_visit_source(
        "https://tr.indeed.com/jobs"
    )

    assert result is True


def test_normal_browsing_without_research_controller():
    browser = BrowserManager()

    result = browser._can_visit_source(
        "https://www.amazon.com"
    )

    assert result is True


def test_blocks_unregistered_dynamic_domain():
    browser, _ = create_browser_with_controller(
        allowed_domains=set(),
        dynamic_sources={
            "Company Career Pages",
        },
    )

    result = browser._can_visit_source(
        "https://careers.microsoft.com/jobs"
    )

    # Dynamic domains must be registered first
    assert result is False


def test_allows_registered_dynamic_domain():
    browser, controller = create_browser_with_controller(
        allowed_domains=set(),
        dynamic_sources={
            "Company Career Pages",
        },
    )

    print(
        "\nDYNAMIC SOURCES:",
        controller.state.dynamic_sources,
    )

    print(
        "DYNAMIC DOMAINS BEFORE:",
        controller.state.dynamic_domains,
    )

    registered = controller.register_dynamic_domain(
        "Company Career Pages",
        "microsoft.com",
    )

    print("REGISTERED RESULT:", registered)

    print(
        "DYNAMIC DOMAINS AFTER:",
        controller.state.dynamic_domains,
    )

    result = browser._can_visit_source(
        "https://careers.microsoft.com/jobs"
    )

    assert registered is True
    assert result is True


def test_fixed_source_cannot_register_dynamic_domain():
    _, controller = create_browser_with_controller(
        allowed_domains={
            "trendyol.com",
        },
        dynamic_sources=set(),
    )

    result = controller.register_dynamic_domain(
        "Trendyol",
        "amazon.com",
    )

    assert result is False

    assert not controller.is_domain_allowed(
        "amazon.com"
    )


def test_dynamic_domain_registration_tool():
    # Comparison state keeps the planned research sources
    comparison_state = ComparisonState(
        query="Find AI internships",
        planned_sources=[
            "Company Career Pages",
        ],
    )

    # Deterministic state keeps browser research rules
    research_state = ResearchState(
        query="Find AI internships",
        dynamic_sources={
            "Company Career Pages",
        },
    )

    controller = ResearchController(
        research_state
    )

    store = ObservationStore()

    # Build research tools with access to the active controller
    tools = {
        tool.name: tool
        for tool in create_research_tools(
            get_state=lambda: comparison_state,
            observation_store=store,
            get_controller=lambda: controller,
        )
    }

    # Registration must fail before the source starts
    blocked = tools[
        "research_register_dynamic_domain"
    ].invoke(
        {
            "source": "Company Career Pages",
            "url": (
                "https://careers.microsoft.com/jobs"
            ),
        }
    )

    assert "BLOCKED" in blocked

    # Start the planned dynamic source
    started = tools[
        "research_start_source"
    ].invoke(
        {
            "source": "Company Career Pages",
        }
    )

    assert "STARTED" in started

    # Register the discovered domain
    registered = tools[
        "research_register_dynamic_domain"
    ].invoke(
        {
            "source": "Company Career Pages",
            "url": (
                "https://careers.microsoft.com/jobs"
            ),
        }
    )

    assert "REGISTERED" in registered

    # The exact discovered domain is allowed
    assert controller.is_domain_allowed(
        "careers.microsoft.com"
    )

    # Do not automatically broaden access to the parent domain
    assert not controller.is_domain_allowed(
        "microsoft.com"
    )