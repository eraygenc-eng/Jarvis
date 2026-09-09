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
    find_best_public_for_source,
    find_best_conditional_for_source,
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

                "For each source, call research_start_source first. "
                "Then browse that source thoroughly and store useful distinct offers "
                "with research_add_result. "

                "If a product is not found immediately, do not conclude NO_RESULTS "
                "after a single search. Use progressively broader discovery queries. "
                "Start with the exact brand and full model name, then try a shorter "
                "model identity, then a broader distinctive model-family query. "
                "For example: "
                "'Logitech G Pro X Superlight 2' -> "
                "'G Pro X Superlight 2' -> "
                "'Superlight'. "

                "After actually performing and inspecting each distinct search, "
                "call research_record_discovery_attempt with the exact query used. "
                "Do not record fake or duplicate attempts just to satisfy the minimum. "

                "When broader searches return related products, distinguish the exact "
                "requested model from different editions, generations, or configurations. "
                "For example, Superlight 2, Superlight 2 SE, and Superlight 2 DEX "
                "must not automatically be treated as equivalent. "
                "Use SKU or model identifiers when visible. "

                "Before calling research_complete_source with COMPLETED, identify the "
                "current cheapest public and conditional winner candidates for that source. "
                "Open each current source winner on its exact seller/provider offer page, "
                "inspect a fresh browser snapshot, and verify the current price, seller, "
                "variant/model/SKU where applicable, fees, availability, and price conditions "
                "with research_verify_result(exact_offer=True). "

                "Only then call research_complete_source. "
                "If completion is blocked because another winner candidate still needs "
                "verification, verify the result IDs reported by the tool and try again. "

                "Only use NO_RESULTS after the required distinct discovery searches were "
                "genuinely attempted and no matching offer was found. "
                "If the source itself cannot be accessed or researched reliably, use "
                "BLOCKED with the real reason instead of NO_RESULTS. "

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


        return (
            "The comparison research is complete and ready "
            "for the final answer."
        )


    def _build_final_research_context(self) -> str:
        state = self.current_comparison_state

        if state is None:
            return "No comparison research data is available."

        lines = []

        # Report every planned source exactly once
        for source in state.planned_sources:
            source_state = state.get_source_state(source)

            if source_state is None:
                lines.append(
                    f"- {source}: source state unavailable"
                )
                continue

            # Keep source status separately so that partial prices
            # are still visible when research becomes blocked.
            source_status = source_state.status.value

            blocked_reason = None

            if source_status == "blocked":
                blocked_reason = (
                    source_state.completion_reason
                    or "Could not be researched."
                )

            # NO_RESULTS should genuinely contain no stored offer.
            if source_status == "no_results":
                lines.append(
                    f"- {source}: NO MATCHING RESULT"
                )
                continue


            # Best prices seen during research,
            # even if exact-page verification failed.
            observed_public = find_best_public_for_source(
                state,
                source,
                verified_only=False,
            )

            observed_conditional = (
                find_best_conditional_for_source(
                    state,
                    source,
                    verified_only=False,
                )
            )

            # Final trusted prices use verified results only.
            best_public = find_best_public_for_source(
                state,
                source,
                verified_only=True,
            )

            best_conditional = (
                find_best_conditional_for_source(
                    state,
                    source,
                    verified_only=True,
                )
            )

            parts = [f"- {source}:"]


            if source_status == "blocked":
                parts.append(
                    "status=BLOCKED"
                )

                if blocked_reason:
                    parts.append(
                        f"reason={blocked_reason}"
                    )

            if observed_public is not None:
                observed_public_total = get_public_total(
                    observed_public
                )

                parts.append(
                    f"observed public={observed_public_total} "
                    f"{observed_public.currency or ''}".strip()
                )

                if observed_public.seller:
                    parts.append(
                        f"observed seller={observed_public.seller}"
                    )

            if observed_conditional is not None:
                observed_conditional_total = (
                    get_conditional_total(
                        observed_conditional
                    )
                )

                parts.append(
                    f"observed conditional="
                    f"{observed_conditional_total} "
                    f"{observed_conditional.currency or ''}".strip()
                )

                if observed_conditional.price_condition:
                    parts.append(
                        f"observed condition="
                        f"{observed_conditional.price_condition}"
                    )

            if best_public is not None:
                public_total = get_public_total(
                    best_public
                )

                parts.append(
                    f"verified public={public_total} "
                    f"{best_public.currency or ''}".strip()
                )

                if best_public.seller:
                    parts.append(
                        f"seller={best_public.seller}"
                    )

            if best_conditional is not None:
                conditional_total = (
                    get_conditional_total(
                        best_conditional
                    )
                )

                parts.append(
                    f"verified conditional="
                    f"{conditional_total} "
                    f"{best_conditional.currency or ''}".strip()
                )

                if best_conditional.price_condition:
                    parts.append(
                        f"condition="
                        f"{best_conditional.price_condition}"
                    )

                if best_conditional.seller:
                    parts.append(
                        f"conditional seller="
                        f"{best_conditional.seller}"
                    )

            if (
                best_public is None
                and best_conditional is None
            ):
                if (
                    observed_public is not None
                    or observed_conditional is not None
                ):
                    parts.append(
                        "PRICE OBSERVED BUT NOT VERIFIED"
                    )
                else:
                    parts.append(
                        "NO PRICE OBSERVED"
                    )

            lines.append(" | ".join(parts))

        winner = (
            state.get_result(
                state.finalized_result_id
            )
            if state.finalized_result_id
            else None
        )

        lines.append("")

        if winner is not None:
            winner_public = get_public_total(
                winner
            )

            winner_conditional = (
                get_conditional_total(
                    winner
                )
            )

            winner_prices = []

            if winner_public is not None:
                winner_prices.append(
                    f"public={winner_public} "
                    f"{winner.currency or ''}".strip()
                )

            if winner_conditional is not None:
                conditional_text = (
                    f"conditional={winner_conditional} "
                    f"{winner.currency or ''}"
                ).strip()

                if winner.price_condition:
                    conditional_text += (
                        f" ({winner.price_condition})"
                    )

                winner_prices.append(
                    conditional_text
                )

            lines.append(
                "FINAL VERIFIED WINNER: "
                f"{winner.source} | "
                f"{winner.title} | "
                + " | ".join(winner_prices)
            )

            if winner.seller:
                lines.append(
                    f"WINNER SELLER: {winner.seller}"
                )

            if winner.verification_url:
                lines.append(
                    "WINNER VERIFIED OFFER URL: "
                    f"{winner.verification_url}"
                )

        else:
            lines.append(
                "FINAL VERIFIED WINNER: None"
            )

        lines.append(
            "FINAL PAGE VERIFIED: "
            f"{state.final_page_verified}"
        )

        if state.final_page_url:
            lines.append(
                f"FINAL PAGE URL: {state.final_page_url}"
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
            and self.current_comparison_state.coverage_complete()
            and self.current_comparison_state.is_finalized()
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
                                "using ONLY the research data below.\n\n"

                                "MANDATORY OUTPUT RULES:\n"
                                "- Report EVERY planned source exactly once.\n"
                                "- Do not omit a source even if it had no result, "
                                "was blocked, or was more expensive than the winner.\n"
                                "- For each source, show the best confirmed public price "
                                "that is available in the research data.\n"
                                "- If an observed price exists but could not be verified, "
                                "show it separately as an observed/unverified price. "
                                "Never present it as confirmed.\n"
                                "- If available, also show membership, Premium, coupon, "
                                "card, loyalty, or other conditional prices separately.\n"
                                "- Clearly distinguish public prices from conditional prices.\n"
                                "- If a source has no matching result, say so.\n"
                                "- If a source could not be researched, say so.\n"
                                "- Never invent or estimate a price that is not present "
                                "in the research data.\n"
                                "- Do not omit the other checked sources just because "
                                "a winner has already been found.\n\n"

                                "After reporting all sources, clearly state the final "
                                "verified winner and its price. "
                                "Mention that the browser has been left open on the "
                                "winner's exact offer page.\n\n"

                                "TRANSACTION RULES:\n"
                                "- Do not add the product to the cart automatically.\n"
                                "- Do not proceed to checkout automatically.\n"
                                "- Do not begin a booking or reservation automatically.\n"
                                "- Do not enter payment or personal information.\n"
                                "- After presenting the comparison, ask the user whether "
                                "they want you to continue with the purchase, booking, "
                                "or reservation process.\n\n"

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