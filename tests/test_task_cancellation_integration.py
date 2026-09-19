import asyncio

from types import SimpleNamespace

from core.context import RequestContext

from core.planning.task_runtime import (
    TaskRuntime,
    TaskCancelledError,
)

from core.planning.action_executor import ActionExecutor

from core.planning.task_cancellation_middleware import (
    TaskCancellationMiddleware,
)


def test_old_tool_result_is_rejected_after_new_task_starts():
    async def run_test():
        # Shared runtime for the whole execution chain
        task_runtime = TaskRuntime()

        # Middleware uses the same task runtime
        middleware = TaskCancellationMiddleware(
            task_runtime
        )

        tool_started = asyncio.Event()
        allow_tool_to_finish = asyncio.Event()

        agent_returned = False

        class FakeAgent:
            async def ainvoke(
                self,
                input_data,
                *,
                config,
                context,
            ):
                nonlocal agent_returned

                # Create the runtime structure expected by middleware
                runtime = SimpleNamespace(
                    context=context
                )

                request = SimpleNamespace(
                    runtime=runtime
                )

                async def slow_tool(request):
                    # Tell the test that the tool has started
                    tool_started.set()

                    # Keep the tool running
                    await allow_tool_to_finish.wait()

                    return "late-tool-result"

                # Run the tool through cancellation middleware
                result = await middleware.awrap_tool_call(
                    request,
                    slow_tool,
                )

                # This must never happen for the cancelled task
                agent_returned = True

                return {
                    "messages": [
                        SimpleNamespace(
                            content=result
                        )
                    ]
                }

        agent = FakeAgent()

        executor = ActionExecutor(
            agent=agent,
            task_runtime=task_runtime,
        )

        # Start Task A
        task_a = task_runtime.start_new_task()

        context_a = RequestContext(
            user_message="first task",
            research_active=False,
            interactive=False,
            task_id=task_a.task_id,
            turn_id=task_a.turn_id,
        )

        async def run_task_a():
            return await executor.execute_agent_turn(
                task=task_a,
                messages=[
                    {
                        "role": "user",
                        "content": "first task",
                    }
                ],
                config={},
                context=context_a,
            )

        # Start Task A in the background
        running_task_a = asyncio.create_task(
            run_task_a()
        )

        # Wait until Task A's tool really starts
        await tool_started.wait()

        # Start Task B while Task A is still running
        task_runtime.start_new_task()

        # Let Task A's old tool finish
        allow_tool_to_finish.set()

        # The old result must be rejected
        try:
            await running_task_a

        except TaskCancelledError:
            pass

        else:
            raise AssertionError(
                "Old task result was not cancelled"
            )

        # Middleware must stop the old result
        # before the fake agent can publish it
        assert agent_returned is False

    asyncio.run(run_test())