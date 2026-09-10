import re
import asyncio

from contextlib import AsyncExitStack # For Playwright Connection
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


from langchain_core.tools import tool

from core.research.evidence import ObservationStore


class BrowserManager:
    def __init__(self):
        self.client = MultiServerMCPClient(
            {
                "playwright": {
                    "command": "cmd",
                    "args": [
                        "/c",
                        "npx",
                        "-y",
                        "@playwright/mcp@latest",
                        "--isolated",
                    ],
                    "transport": "stdio",
                }
            }
        )

        # Keep async connections open
        self.exit_stack = AsyncExitStack()

        # Store the active MCP session
        self.session = None

        # Store Playwright browser tools
        self.tools = None

        # Keep browser observations in this browser session.
        self.observations = ObservationStore()
        self._action_lock = asyncio.Lock()

    async def _track_browser_action(self, request, handler):
        # One shared browser must not navigate and capture different pages at once.
        async with self._action_lock:
            self.observations.invalidate_current()
            return await handler(request)


    async def capture_snapshot(self) -> str:
        async with self._action_lock:
            self.observations.invalidate_current()
            return await self._capture_snapshot()

    async def _capture_snapshot(self) -> str:
        if self.session is None:
            return "OBSERVATION FAILED: Browser session is not started."

        # Read directly from the existing MCP session.
        response = await self.session.call_tool(
            "browser_snapshot",
            arguments={},
        )

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        ).replace("\r\n", "\n")

        if response.isError:
            return f"OBSERVATION FAILED: Browser returned an error.\n{text}"

        # Read the URL from MCP page metadata, not from page links.
        page_match = re.search(
            r"(?m)^### Page(?: state)?\n- Page URL: (https?://[^\s]+)",
            text,
        )

        # Support the known MCP snapshot section formats.
        snapshot_match = re.search(
            r"(?ms)^(?:### Snapshot|- Page Snapshot:)[ \t]*\n"
            r"```(?:yaml)?\n(.*?)\n```",
            text,
        )

        if page_match is None or snapshot_match is None:
            return (
                "OBSERVATION NOT STORED: "
                "The browser output format could not be parsed. "
                "Do not use this response as a stored observation.\n\n"
                + text
            )

        page_url = page_match.group(1)
        page_text = snapshot_match.group(1)

        if not page_text.strip():
            return (
                "OBSERVATION NOT STORED: The page snapshot is empty.\n\n"
                + text
            )

        observation = self.observations.capture(
            page_url=page_url,
            page_text=page_text,
        )

        return (
            f"Observation ID: {observation.observation_id}\n"
            f"Captured at: {observation.captured_at.isoformat()}\n"
            "This records page content, not a verified offer.\n\n"
            + text
        )

    async def start(self):
        # Open a persistent Playwright MCP session
        self.session = await self.exit_stack.enter_async_context(
            self.client.session("playwright")
        )

        # Load Playwright tools for LangChain
        self.tools = await load_mcp_tools(
            self.session,
            tool_interceptors=[self._track_browser_action],
        )

        @tool
        async def browser_snapshot() -> str:
            """
            Read the current page and store a browser observation.

            Returns an observation ID when capture succeeds.
            The observation alone does not verify a price or seller.
            """
            return await self.capture_snapshot()

        # Replace only the agent-facing snapshot tool.
        self.tools = [
            existing_tool
            for existing_tool in self.tools
            if existing_tool.name != "browser_snapshot"
        ]

        self.tools.append(browser_snapshot)

    async def stop(self):
        self.observations.invalidate_current()
        # Close all async connections
        await self.exit_stack.aclose()

        # Clear stored session and tools
        self.session = None
        self.tools = None


    def get_tools(self):
        # Return loaded browser tools
        if self.tools is None:
            raise RuntimeError("BrowserManager is not started.")

        return self.tools
