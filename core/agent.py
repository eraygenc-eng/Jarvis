import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from core.llm.base import BaseLLM
from core.prompts import JARVIS_SYSTEM_PROMPT


from core.research.task_classifier import TaskType, classify_task
from core.research.research_manager import create_comparison_state
from core.research.research_tools import create_research_tools

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

        # Store the active comparison research state
        self.current_comparison_state = None

        MAX_RESEARCH_CONTINUATIONS = 3

        # Create tools that can access the active research state
        research_tools = create_research_tools(
            lambda: self.current_comparison_state
        )

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

        # Add comparison research tools
        tools.extend(research_tools)

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
        # Detect what kind of task the user requested
        task_type = classify_task(prompt)


        # Continue an unfinished comparison across follow-up user messages
        active_comparison = (
            self.current_comparison_state is not None
            and not self.current_comparison_state.is_ready_to_return()
        )

        if active_comparison:
            task_type = TaskType.COMPARISON


        # Create a new research state only when starting a new comparison
        if (
            task_type == TaskType.COMPARISON
            and not active_comparison
        ):
            self.current_comparison_state = await create_comparison_state(
                prompt,
                self.llm,
            )


        # Configuration shared across agent calls
        config = {
            "configurable": {
                "thread_id": self.thread_id
            },
            # Track LLM and tool execution times
            "callbacks": [self.timing_callback],
        }


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

        # Continue comparison research until it is properly finalized
        if task_type == TaskType.COMPARISON:
            continuation_count = 0

            while (
                self.current_comparison_state is not None
                and not self.current_comparison_state.is_ready_to_return()
                and continuation_count < self.MAX_RESEARCH_CONTINUATIONS
            ):
                continuation_count += 1

                result = await self.agent.ainvoke(
                    {
                        "messages": [
                            (
                                "user",
                                (
                                    "The comparison research is not ready to return yet. "
                                    "Continue the existing research. Check research_status. "
                                    "If the strongest candidates are not verified, verify them on their "
                                    "exact pages using research_verify_result. "
                                    "If no winner has been finalized, call research_finalize with a "
                                    "verified winner. "
                                    "After finalization, navigate to the finalized winner's exact page, "
                                    "confirm from a fresh browser snapshot that the correct result is "
                                    "actually visible, and then call research_confirm_final_page. "
                                    "Do not give the final answer until these steps are complete."
                                ),
                            )
                        ]
                    },
                    config=config,
                )

        # Prevent an unverified comparison from being returned as final
        if (
            task_type == TaskType.COMPARISON
            and self.current_comparison_state is not None
            and not self.current_comparison_state.is_ready_to_return()
        ):
            result = await self.agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "The comparison could not be finalized after the allowed "
                                "verification attempts. Do not use any more tools. "
                                "Do not present any unverified result as a confirmed winner. "
                                "Explain that the strongest candidates could not be "
                                "sufficiently verified and clearly state the limitation."
                            ),
                        }
                    ]
                },
                config=config,
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

    