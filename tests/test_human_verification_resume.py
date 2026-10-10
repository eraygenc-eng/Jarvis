
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mcp.types import CallToolResult, TextContent

from core.tools.browser import BrowserManager
from core.browser_action_policy import current_observation_is_visible
from langchain_core.messages import ToolMessage


class HumanVerificationResumeTests(
    unittest.IsolatedAsyncioTestCase
):

    async def test_manual_verification_allows_fresh_snapshot(self):
        manager = BrowserManager()

        # Simulate a page with human verification.
        captcha_page = (
            "### Page\n"
            "- Page URL: https://example.com/\n"
            "### Snapshot\n"
            "```yaml\n"
            "- text: CAPTCHA verification required\n"
            '- button "Verify" [ref=e1]\n'
            "```"
        )

        # Simulate the normal page after manual verification.
        normal_page = (
            "### Page\n"
            "- Page URL: https://example.com/\n"
            "### Snapshot\n"
            "```yaml\n"
            '- textbox "From" [ref=e2]\n'
            '- textbox "To" [ref=e3]\n'
            "```"
        )

        def tool_response(text):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=text,
                    )
                ],
                isError=False,
            )

        # Return CAPTCHA first, then the normal page.
        manager.session = SimpleNamespace(
            call_tool=AsyncMock(
                side_effect=[
                    tool_response(captcha_page),
                    tool_response(normal_page),
                ]
            )
        )

        # First snapshot detects the CAPTCHA.
        first = await manager.capture_snapshot(
            focus="Flight form",
            mode="interactive",
        )

        self.assertTrue(
            manager._waiting_for_human_verification
        )

        # The CAPTCHA observation must not hide browser_snapshot.
        self.assertIsNone(
            manager.observations.current_observation_id
        )

        self.assertTrue(manager._page_changed)

        # Simulate the user completing verification.
        second = await manager.capture_snapshot(
            focus="Flight form",
            mode="interactive",
        )

        # Jarvis must recognize the normal page.
        self.assertFalse(
            manager._waiting_for_human_verification
        )

        self.assertIsNotNone(
            manager.observations.current_observation_id
        )

        self.assertFalse(manager._page_changed)

        self.assertIn('textbox "From"', second)
        self.assertIn('textbox "To"', second)

        # The refreshed observation should be usable.
        message = ToolMessage(
            content=second,
            tool_call_id="snapshot-call",
            name="browser_snapshot",
        )

        self.assertTrue(
            current_observation_is_visible(
                [message],
                manager.observations,
            )
        )


if __name__ == "__main__":
    unittest.main()
