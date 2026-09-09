import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from core.llm.base import BaseLLM
from core.prompts import JARVIS_SYSTEM_PROMPT

from core.research.task_classifier import (
    TaskType,
    classify_task,
)

from core.research.research_manager import (
    create_comparison_state,
)

from core.research.research_tools import (
    create_research_tools,
)

from core.research.ranking import (
    find_best_public,
    find_best_conditional,
    find_best_overall,
    get_public_total,
    get_conditional_total,
)

from core.tools.calculator import calculator
from core.tools.open_application import open_application
from core.tools.close_application import close_application
from core.tools.launch_game import launch_game
from core.tools.web_search import web_search_tool

from core.security.middleware import security_middleware
from core.callbacks.timing import TimingCallback


class JarvisAgent:
    def __init__(
        self,
        llm: BaseLLM,
        browser_tools=None,
    ):
        self.llm = llm

        # Keeps conversation history in memory
        self.memory = InMemorySaver()

        # Unique ID for this conversation
        self.thread_id = str(uuid.uuid4())

        # Active comparison research
        self.current_comparison_state = None

        # Prevent endless research continuation loops
        self.max_research_continuations = 4

        # Research tools use the active comparison state
        research_tools = create_research_tools(
            lambda: self.current_comparison_state
        )

        # Measure model and tool execution times
        self.timing_callback = TimingCallback()

        tools = [
            calculator,
            open_application,
            close_application,
            launch_game,
            web_search_tool,
        ]

        tools.extend(research_tools)

        if browser_tools:
            tools.extend(browser_tools)

        self.agent = create_agent(
            model=self.llm.get_model(),
            tools=tools,
            system_prompt=JARVIS_SYSTEM_PROMPT,
            middleware=[
                security_middleware,
                ModelFallbackMiddleware(
                    self.llm.get_fallback_model()
                ),
            ],
            checkpointer=self.memory,
        )

    def _build_research_continuation_prompt(
        self,
    ) -> str:
        state = self.current_comparison_state

        if state is None:
            return (
                "There is no active comparison research."
            )

        # Phase 1: source coverage
        if not state.coverage_complete():
            remaining_sources = [
                source_state.source
                for source_state in state.source_states.values()
                if not source_state.is_terminal()
            ]

            return (
                "The comparison research is not complete yet. "
                f"Remaining sources: {remaining_sources}. "
                "Continue researching the remaining planned sources one by one. "
                "For each source, call research_start_source, browse the source thoroughly, "
                "and store useful distinct offers with research_add_result. "
                "Before calling research_complete_source, identify the current cheapest "
                "public and conditional winner candidates for that source. "
                "Open each current source winner on its exact seller/provider offer page, "
                "inspect a fresh browser snapshot, and verify the current price, seller, "
                "variant/model/SKU where applicable, fees, availability, and price conditions "
                "with research_verify_result(exact_offer=True). "
                "Only then call research_complete_source. "
                "If source completion is blocked because another winner candidate still "
                "needs verification, verify the result IDs reported by the tool and try "
                "research_complete_source again. "
                "Do not stop early because one cheap offer has already been found."
            )

        # Phase 2: ranking, verification, and winner selection
        if not state.is_finalized():
            return (
                "Source coverage is complete, but the comparison "
                "has not been finalized. Call research_rankings. "
                "Verify the strongest candidates on their exact "
                "seller or provider pages using "
                "research_verify_result with "
                'verification_type="exact_offer". '
                "Then call research_rankings with "
                "verified_only=True and finalize the correct "
                "verified winner with research_finalize."
            )

        # Phase 3: final browser position
        if not state.final_page_verified:
            return (
                "The comparison winner is finalized. "
                "Navigate to the finalized winner's exact verified "
                "offer page, take a fresh browser snapshot, confirm "
                "that the correct result is visible, and then call "
                "research_confirm_final_page. "
                "Do not return the final answer until the final "
                "browser page has been confirmed."
            )

        # Phase 4: safe transaction staging
        if (
            state.requires_staging
            and not state.staging_finished()
        ):
            return (
                "The finalized winner page is confirmed, but "
                "transaction staging is still pending. "
                "Continue toward the normal purchase, checkout, "
                "booking, or reservation flow for the finalized "
                "winner. You may perform reversible steps such as "
                "selecting the verified offer, adding a product to "
                "the cart, opening the cart, proceeding to checkout, "
                "or reaching booking or passenger detail pages. "
                "Stop before payment, placing an order, confirming "
                "a booking, purchasing a ticket, or another "
                "irreversible transaction. "
                "Take a fresh browser snapshot at the safest useful "
                "pre-commit point and call "
                "research_confirm_staging_page. "
                "If staging cannot continue safely because login, "
                "personal information, payment information, or "
                "another sensitive requirement is needed, call "
                "research_mark_staging_blocked instead."
            )

        return (
            "The comparison research is complete and ready "
            "for the final answer."
        )


    def _build_final_research_context(self) -> str:
        state = self.current_comparison_state

        if state is None:
            return "No comparison research data is available."

        lines = []

        # Build one summary for every planned source
        for source in state.planned_sources:
            source_state = state.get_source_state(source)

            if source_state is None:
                continue

            if source_state.status.value == "blocked":
                lines.append(
                    f"- {source}: BLOCKED - "
                    f"{source_state.completion_reason or 'Could not be researched.'}"
                )
                continue

            if source_state.status.value == "no_results":
                lines.append(
                    f"- {source}: NO MATCHING RESULT"
                )
                continue

            source_results = state.get_results_for_source(source)

            public_results = [
                result
                for result in source_results
                if get_public_total(result) is not None
            ]

            conditional_results = [
                result
                for result in source_results
                if get_conditional_total(result) is not None
            ]

            best_public = (
                min(
                    public_results,
                    key=get_public_total,
                )
                if public_results
                else None
            )

            best_conditional = (
                min(
                    conditional_results,
                    key=get_conditional_total,
                )
                if conditional_results
                else None
            )

            parts = [f"- {source}:"]

            if best_public is not None:
                parts.append(
                    f"public={get_public_total(best_public)} "
                    f"{best_public.currency or ''}".strip()
                )

            if best_conditional is not None:
                parts.append(
                    f"conditional={get_conditional_total(best_conditional)} "
                    f"{best_conditional.currency or ''} "
                    f"({best_conditional.price_condition})".strip()
                )

            if (
                best_public is None
                and best_conditional is None
            ):
                parts.append(
                    "price could not be determined"
                )

            lines.append(" ".join(parts))

        best_public = find_best_public(
            state,
            verified_only=False,
        )

        best_conditional = find_best_conditional(
            state,
            verified_only=False,
        )

        winner = (
            state.get_result(state.finalized_result_id)
            if state.finalized_result_id
            else None
        )

        lines.append("")
        lines.append(
            "Best public: "
            + (
                f"{best_public.source} | "
                f"{best_public.title} | "
                f"{get_public_total(best_public)} "
                f"{best_public.currency or ''}"
                if best_public
                else "None"
            )
        )

        lines.append(
            "Best conditional: "
            + (
                f"{best_conditional.source} | "
                f"{best_conditional.title} | "
                f"{get_conditional_total(best_conditional)} "
                f"{best_conditional.currency or ''} | "
                f"{best_conditional.price_condition}"
                if best_conditional
                else "None"
            )
        )

        lines.append(
            "Final verified winner: "
            + (
                f"{winner.source} | "
                f"{winner.title}"
                if winner
                else "None"
            )
        )

        lines.append(
            f"Staging status: {state.staging_status.value}"
        )

        if state.staging_notes:
            lines.append(
                f"Staging notes: {state.staging_notes}"
            )

        return "\n".join(lines)

    

    def _get_config(self) -> dict:
        return {
            "configurable": {
                "thread_id": self.thread_id,
            },
            "callbacks": [
                self.timing_callback,
            ],
        }

    async def run(
        self,
        prompt: str,
    ) -> str:
        # Detect the task requested by the user
        task_type = classify_task(prompt)

        # Continue unfinished comparison research
        active_comparison = (
            self.current_comparison_state is not None
            and not self.current_comparison_state.is_ready_to_return()
        )

        if active_comparison:
            task_type = TaskType.COMPARISON

        # Create a new comparison state only for a new comparison
        if (
            task_type == TaskType.COMPARISON
            and not active_comparison
        ):
            self.current_comparison_state = (
                await create_comparison_state(
                    prompt,
                    self.llm,
                )
            )

        config = self._get_config()

        # Send the original user request to the agent
        result = await self.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            },
            config=config,
        )

        # Continue comparison research when the model stops early
        if task_type == TaskType.COMPARISON:
            continuation_count = 0

            while (
                self.current_comparison_state is not None
                and not self.current_comparison_state.is_ready_to_return()
                and continuation_count
                < self.max_research_continuations
            ):
                continuation_count += 1

                continuation_prompt = (
                    self._build_research_continuation_prompt()
                )

                result = await self.agent.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": continuation_prompt,
                            }
                        ]
                    },
                    config=config,
                )

        # Do not present an unfinished comparison as confirmed
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
                                "The comparison could not be fully "
                                "completed within the allowed research "
                                "continuations. Do not use more tools. "
                                "Do not present an unverified or "
                                "unfinished result as a confirmed winner. "
                                "Briefly explain what remains incomplete."
                            ),
                        }
                    ]
                },
                config=config,
            )

        # Generate a complete final comparison report
        if (
            task_type == TaskType.COMPARISON
            and self.current_comparison_state is not None
            and self.current_comparison_state.is_ready_to_return()
        ):
            research_context = (
                self._build_final_research_context()
            )

            result = await self.agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "The comparison workflow is complete. "
                                "Do not use any more tools. "
                                "Give the user the final comparison report "
                                "using the research data below.\n\n"
                                "Report every planned source and the best "
                                "price found there. Clearly distinguish "
                                "public prices from conditional or membership "
                                "prices. Mention sources with no result or "
                                "that could not be researched. Then state the "
                                "final verified winner and briefly explain "
                                "where the browser was left. "
                                "Do not omit the other checked sources just "
                                "because a winner has already been found.\n\n"
                                "RESEARCH DATA:\n"
                                f"{research_context}"
                            ),
                        }
                    ]
                },
                config=config,
            )
        

        # Get the final Jarvis response
        content = result["messages"][-1].content

        # Some models return text blocks
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                )
            )

        return content