import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent import JarvisAgent
from core.research.research_manager import ComparisonSetup
from core.research.source_planner import SourceSelection
from core.research.task_classifier import TaskType


def create_test_agent() -> JarvisAgent:
    # Create Jarvis without running the real constructor
    agent = object.__new__(JarvisAgent)

    # Minimal state required by Jarvis.run()
    agent.llm = object()
    agent.thread_id = "test-thread"

    agent.current_comparison_state = None
    agent.research_controller = None

    agent.pending_comparison_prompt = None
    agent.pending_source_count = None

    agent.max_research_continuations = 20
    agent.max_stalled_research_continuations = 2

    # Fake timing callback
    agent.timing_callback = SimpleNamespace(
        reset_request_stats=MagicMock(),
        print_summary=MagicMock(),
    )

    # Fake task runtime
    agent.task_runtime = SimpleNamespace(
        start_new_task=MagicMock(
            return_value=SimpleNamespace(
                task_id="task-1",
                turn_id="turn-1",
            )
        ),
        complete_task=MagicMock(),
        fail_task=MagicMock(),
        ensure_current=MagicMock(),
    )

    # Fake action executor
    agent.action_executor = SimpleNamespace(
        execute_agent_turn=AsyncMock()
    )

    return agent


class SourceClarificationTests(
    unittest.IsolatedAsyncioTestCase
):

    async def test_source_clarification_stops_before_agent_execution(
        self,
    ):
        agent = create_test_agent()

        prompt = "En ucuz iPhone'u 3 siteye bakarak bul"

        setup = ComparisonSetup(
            state=None,
            source_selection=SourceSelection(
                sources=[],
                needs_clarification=True,
                requested_count=3,
            ),
        )

        with (
            patch(
                "core.agent.classify_task",
                return_value=TaskType.COMPARISON,
            ),
            patch(
                "core.agent.create_comparison_state",
                new=AsyncMock(return_value=setup),
            ),
        ):
            response = await agent.run(prompt)

        self.assertEqual(
            response,
            "Hangi 3 siteye bakmamı istersiniz?",
        )

        # Original request should be preserved
        self.assertEqual(
            agent.pending_comparison_prompt,
            prompt,
        )
        self.assertEqual(
            agent.pending_source_count,
            3,
        )

        # Research should not start
        self.assertIsNone(
            agent.current_comparison_state
        )
        self.assertIsNone(
            agent.research_controller
        )

        # No agent or browser execution should happen
        agent.action_executor.execute_agent_turn.assert_not_awaited()

        agent.task_runtime.complete_task.assert_called_once_with(
            "task-1"
        )


    async def test_source_clarification_response_restores_original_request(
        self,
    ):
        agent = create_test_agent()

        original_prompt = (
            "En ucuz iPhone'u 3 siteye bakarak bul"
        )

        # Simulate waiting for the source answer
        agent.pending_comparison_prompt = original_prompt
        agent.pending_source_count = 3

        source_answer = (
            "Trendyol, Akakce ve Hepsiburada"
        )

        # Fake resolved comparison state
        comparison_state = SimpleNamespace(
            final_page_verified=False,
            planned_sources = [],
            is_ready_to_return=lambda: True,
        )

        setup = ComparisonSetup(
            state=comparison_state,
            source_selection=SourceSelection(
                sources=[
                    "Trendyol",
                    "Hepsiburada",
                    "Akakce",
                ],
                needs_clarification=False,
                requested_count=3,
            ),
        )

        agent.action_executor.execute_agent_turn = AsyncMock(
            return_value={
                "messages": []
            }
        )

        # Do not run the real report model here
        agent._generate_research_report = AsyncMock(
            return_value="Research complete"
        )

        with patch(
            "core.agent.create_comparison_state",
            new=AsyncMock(return_value=setup),
        ) as create_state_mock:
            response = await agent.run(
                source_answer
            )

        self.assertEqual(
            response,
            "Research complete",
        )

        # Clarification state should be cleared
        self.assertIsNone(
            agent.pending_comparison_prompt
        )
        self.assertIsNone(
            agent.pending_source_count
        )

        # Research state should now exist
        self.assertIs(
            agent.current_comparison_state,
            comparison_state,
        )

        # Original request should be restored
        call = create_state_mock.await_args

        self.assertEqual(
            call.args[0],
            original_prompt,
        )

        source_prompt = call.kwargs[
            "source_prompt"
        ]

        self.assertIn(
            original_prompt,
            source_prompt,
        )
        self.assertIn(
            source_answer,
            source_prompt,
        )

        # Research agent should receive
        # the original research request
        executor_call = (
            agent.action_executor
            .execute_agent_turn
            .await_args
        )

        messages = executor_call.kwargs[
            "messages"
        ]

        self.assertEqual(
            messages[0]["content"],
            original_prompt,
        )

        # Final report should also use
        # the original research request
        agent._generate_research_report.assert_awaited_once()

        report_call = (
            agent._generate_research_report
            .await_args
        )

        self.assertEqual(
            report_call.args[0],
            original_prompt,
        )


if __name__ == "__main__":
    unittest.main()