from core.research.research_controller import ResearchController
from core.research.research_state import ResearchState
from core.tools.browser import BrowserManager

import asyncio
from types import SimpleNamespace

from mcp.types import CallToolResult, TextContent


def test_browser_returns_none_without_controller_getter():
    browser = BrowserManager()

    # No getter means research guard is disabled
    assert browser._get_research_controller() is None


def test_browser_gets_current_controller_dynamically():
    browser = BrowserManager()

    current = {
        "controller": None,
    }

    # Browser asks this function for the current controller
    browser.set_research_controller_getter(
        lambda: current["controller"]
    )

    # No research is active yet
    assert browser._get_research_controller() is None

    state = ResearchState(query="test")
    controller = ResearchController(state)

    # Simulate a research controller becoming active later
    current["controller"] = controller

    assert browser._get_research_controller() is controller


def test_browser_blocks_duplicate_navigation_in_same_turn():
    browser = BrowserManager()

    state = ResearchState(query="test")
    controller = ResearchController(state)

    # Browser should use this research controller
    browser.set_research_controller_getter(
        lambda: controller
    )

    request = SimpleNamespace(
        name="browser_navigate",
        args={
            "url": "https://example.com/product?id=5",
        },
    )

    handler_calls = []

    async def handler(request):
        # Record every real Playwright call
        handler_calls.append(request.args["url"])

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="Navigation completed",
                )
            ],
            isError=False,
        )

    async def run_test():
        first_response = await browser._track_browser_action(
            request,
            handler,
        )

        second_response = await browser._track_browser_action(
            request,
            handler,
        )

        return first_response, second_response

    first_response, second_response = asyncio.run(run_test())

    # First navigation should reach Playwright
    assert len(handler_calls) == 1

    assert first_response.isError is False

    # Second navigation should be skipped before Playwright
    assert "NAVIGATION SKIPPED" in second_response.content[0].text


def test_browser_blocks_tracking_variant_in_same_turn():
    browser = BrowserManager()

    state = ResearchState(query="test")
    controller = ResearchController(state)

    # Browser should use this research controller
    browser.set_research_controller_getter(
        lambda: controller
    )

    first_request = SimpleNamespace(
        name="browser_navigate",
        args={
            "url": (
                "https://example.com/product"
                "?id=5&utm_source=google"
            ),
        },
    )

    second_request = SimpleNamespace(
        name="browser_navigate",
        args={
            "url": (
                "https://example.com/product"
                "?id=5&utm_source=instagram"
            ),
        },
    )

    handler_calls = []

    async def handler(request):
        # Record every real Playwright call
        handler_calls.append(request.args["url"])

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="Navigation completed",
                )
            ],
            isError=False,
        )

    async def run_test():
        await browser._track_browser_action(
            first_request,
            handler,
        )

        return await browser._track_browser_action(
            second_request,
            handler,
        )

    second_response = asyncio.run(run_test())

    # Tracking variants should count as the same page
    assert len(handler_calls) == 1

    # Second navigation should be skipped
    assert "NAVIGATION SKIPPED" in second_response.content[0].text