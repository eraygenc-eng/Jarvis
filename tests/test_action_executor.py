import asyncio

import pytest

from core.planning.action_executor import ActionExecutor
from core.planning.task_runtime import (
    TaskCancelledError,
    TaskRuntime,
)


class FakeAgent:
    def __init__(self):
        self.call_count = 0

    async def ainvoke(
        self,
        input_data,
        *,
        config,
        context,
    ):
        # Count how many times the agent was called
        self.call_count += 1

        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": "done",
                }
            ]
        }


class SupersedingAgent:
    def __init__(self, task_runtime: TaskRuntime):
        self.task_runtime = task_runtime
        self.call_count = 0

    async def ainvoke(
        self,
        input_data,
        *,
        config,
        context,
    ):
        # Count the agent call
        self.call_count += 1

        # Simulate a new user turn
        self.task_runtime.start_new_task()

        # Return a late result from the old task
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": "old result",
                }
            ]
        }


def test_executor_returns_result_for_active_task():
    runtime = TaskRuntime()
    task = runtime.start_new_task()

    agent = FakeAgent()

    executor = ActionExecutor(
        agent=agent,
        task_runtime=runtime,
    )

    async def run_test():
        return await executor.execute_agent_turn(
            task=task,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            config={},
            context=None,
        )

    result = asyncio.run(run_test())

    assert agent.call_count == 1
    assert result["messages"][-1]["content"] == "done"


def test_executor_does_not_run_cancelled_task():
    runtime = TaskRuntime()

    # Create the first task
    old_task = runtime.start_new_task()

    # Starting a new task cancels the old task
    runtime.start_new_task()

    agent = FakeAgent()

    executor = ActionExecutor(
        agent=agent,
        task_runtime=runtime,
    )

    async def run_test():
        await executor.execute_agent_turn(
            task=old_task,
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            config={},
            context=None,
        )

    with pytest.raises(TaskCancelledError):
        asyncio.run(run_test())

    # The cancelled task must not reach the agent
    assert agent.call_count == 0


def test_executor_blocks_late_result_from_old_task():
    runtime = TaskRuntime()
    old_task = runtime.start_new_task()

    agent = SupersedingAgent(runtime)

    executor = ActionExecutor(
        agent=agent,
        task_runtime=runtime,
    )

    async def run_test():
        await executor.execute_agent_turn(
            task=old_task,
            messages=[
                {
                    "role": "user",
                    "content": "research mouse",
                }
            ],
            config={},
            context=None,
        )

    with pytest.raises(TaskCancelledError):
        asyncio.run(run_test())

    # The agent started, but its old result must be blocked
    assert agent.call_count == 1