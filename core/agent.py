import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from core.llm.base import BaseLLM
from core.prompts import JARVIS_SYSTEM_PROMPT

from core.tools.calculator import calculator
from core.tools.open_application import open_application
from core.tools.close_application import close_application
from core.tools.launch_game import launch_game
from core.tools.web_search import web_search_tool
from core.security.middleware import security_middleware


from core.callbacks.timing import TimingCallback


# Main Jarvis agent
class JarvisAgent:
    def __init__(self, llm: BaseLLM, browser_tools=None):
        self.llm = llm

        # Keeps conversation history in memory.
        self.memory = InMemorySaver()

        # Unique ID for this conversation.
        self.thread_id = str(uuid.uuid4())

        # Measure LLM and tool execution times
        self.timing_callback = TimingCallback()

        # Create the main tool list
        tools = [
            calculator,
            open_application,
            close_application,
            launch_game,
            web_search_tool,
        ]

        # Add browser tools if available
        if browser_tools:
            tools.extend(browser_tools)


        # Creates the LangChain agent with tools and fallback model.
        self.agent = create_agent(
            model=self.llm.get_model(),
            tools=tools,
            system_prompt=JARVIS_SYSTEM_PROMPT,
            middleware=[
                security_middleware,
                ModelFallbackMiddleware(
                    self.llm.get_fallback_model()
                )
            ],
            checkpointer=self.memory,
        )

    async def run(self, prompt: str) -> str:
        # Sends the user message to the agent.
        result = await self.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            },
            config={
                "configurable": {
                    "thread_id": self.thread_id
                },

                # Track LLM and tool execution times
                "callbacks": [self.timing_callback],
            },
        )

        # Gets the final Jarvis message.
        content = result["messages"][-1].content

        # Some models may return the response as text blocks.
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

        return content

    