import unittest
from unittest.mock import AsyncMock

from mcp.types import CallToolResult, TextContent

from core.tools.browser import BrowserManager


class FakeRequest:
    def __init__(
        self,
        name: str,
        args: dict | None = None,
    ):
        self.name = name
        self.args = args or {}


class BrowserAutoObservationTests(
    unittest.IsolatedAsyncioTestCase
):

    async def test_click_auto_observes_with_active_focus(self):
        manager = BrowserManager()

        manager._last_snapshot_focus = "iPhone 18 Pro"

        manager._capture_snapshot = AsyncMock(
            return_value=(
                "Observation ID: obs-new\n"
                "Captured at: 2026-09-27T11:00:00\n"
                "- Page URL: https://example.com/product\n"
                "Snapshot mode: focused\n\n"
                "### Snapshot\n"
                "```yaml\n"
                "iPhone 18 Pro - 99.999 TL\n"
                "```"
            )
        )

        request = FakeRequest(
            name="browser_click",
            args={},
        )

        async def handler(_request):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Clicked element successfully.",
                    )
                ],
                isError=False,
            )

        response = await manager._track_browser_action(
            request,
            handler,
        )

        manager._capture_snapshot.assert_awaited_once_with(
            focus="iPhone 18 Pro"
        )

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        self.assertIn(
            "Clicked element successfully.",
            text,
        )

        self.assertIn(
            "AUTO CURRENT PAGE OBSERVATION",
            text,
        )

        self.assertIn(
            "Observation ID: obs-new",
            text,
        )

        self.assertIn(
            "iPhone 18 Pro - 99.999 TL",
            text,
        )

    async def test_click_does_not_auto_observe_without_focus(self):
        manager = BrowserManager()

        manager._last_snapshot_focus = None

        manager._capture_snapshot = AsyncMock(
            return_value="SHOULD NOT BE CALLED"
        )

        request = FakeRequest(
            name="browser_click",
            args={},
        )

        async def handler(_request):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Clicked element successfully.",
                    )
                ],
                isError=False,
            )

        response = await manager._track_browser_action(
            request,
            handler,
        )

        manager._capture_snapshot.assert_not_awaited()

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        self.assertNotIn(
            "AUTO CURRENT PAGE OBSERVATION",
            text,
        )

        self.assertEqual(
            text,
            "Clicked element successfully.",
        )

    async def test_failed_click_does_not_auto_observe(self):
        manager = BrowserManager()

        manager._last_snapshot_focus = "iPhone 18 Pro"

        manager._capture_snapshot = AsyncMock(
            return_value="SHOULD NOT BE CALLED"
        )

        request = FakeRequest(
            name="browser_click",
            args={},
        )

        async def handler(_request):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Click failed.",
                    )
                ],
                isError=True,
            )

        response = await manager._track_browser_action(
            request,
            handler,
        )

        manager._capture_snapshot.assert_not_awaited()

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        self.assertNotIn(
            "AUTO CURRENT PAGE OBSERVATION",
            text,
        )

    async def test_navigate_auto_observes_with_active_focus(self):
        manager = BrowserManager()

        manager._last_snapshot_focus = "iPhone 18 Pro Max"

        manager._capture_snapshot = AsyncMock(
            return_value=(
                "Observation ID: obs-navigate\n"
                "Captured at: 2026-09-27T12:00:00\n"
                "- Page URL: https://example.com/product\n"
                "Snapshot mode: focused\n\n"
                "### Snapshot\n"
                "```yaml\n"
                "iPhone 18 Pro Max - 149.999 TL\n"
                "```"
            )
        )

        request = FakeRequest(
            name="browser_navigate",
            args={
                "url": "https://example.com/product"
            },
        )

        async def handler(_request):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Navigated successfully.",
                    )
                ],
                isError=False,
            )

        response = await manager._track_browser_action(
            request,
            handler,
        )

        manager._capture_snapshot.assert_awaited_once_with(
            focus="iPhone 18 Pro Max"
        )

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        self.assertIn(
            "AUTO CURRENT PAGE OBSERVATION",
            text,
        )

        self.assertIn(
            "Observation ID: obs-navigate",
            text,
        )

        self.assertIn(
            "iPhone 18 Pro Max - 149.999 TL",
            text,
        )

    async def test_navigate_does_not_auto_observe_without_focus(self):
        manager = BrowserManager()

        manager._last_snapshot_focus = None

        manager._capture_snapshot = AsyncMock(
            return_value="SHOULD NOT BE CALLED"
        )

        request = FakeRequest(
            name="browser_navigate",
            args={
                "url": "https://example.com/product"
            },
        )

        async def handler(_request):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Navigated successfully.",
                    )
                ],
                isError=False,
            )

        response = await manager._track_browser_action(
            request,
            handler,
        )

        manager._capture_snapshot.assert_not_awaited()

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        self.assertNotIn(
            "AUTO CURRENT PAGE OBSERVATION",
            text,
        )

        self.assertEqual(
            text,
            "Navigated successfully.",
        )

    def test_reset_request_focus_preserves_current_observation(self):
        manager = BrowserManager()

        observation = manager.observations.capture(
            "https://example.com/product",
            "current product page",
        )

        manager._last_snapshot_focus = "iPhone 18 Pro Max"
        manager._page_changed = False

        manager.reset_request_focus()

        # Old semantic focus must not leak into the next user request.
        self.assertIsNone(
            manager._last_snapshot_focus
        )

        # The actual current browser observation must survive.
        self.assertEqual(
            manager.observations.current_observation_id,
            observation.observation_id,
        )

        # Resetting semantic focus must not dirty the current page.
        self.assertFalse(
            manager._page_changed
        )


if __name__ == "__main__":
    unittest.main()