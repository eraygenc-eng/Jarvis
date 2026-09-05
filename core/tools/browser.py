from contextlib import AsyncExitStack # For Playwright Connection
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


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
                        "--extension",
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

    async def start(self):
        # Open a persistent Playwright MCP session
        self.session = await self.exit_stack.enter_async_context(
            self.client.session("playwright")
        )

        # Load Playwright tools for LangChain
        self.tools = await load_mcp_tools(self.session)

    async def stop(self):
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