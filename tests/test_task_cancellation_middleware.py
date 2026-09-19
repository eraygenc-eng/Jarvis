import asyncio
import pytest

from types import SimpleNamespace

from core.context import RequestContext
from core.planning.task_runtime import (
    TaskRuntime,
    TaskCancelledError,
)
from core.planning.task_cancellation_middleware import (
    TaskCancellationMiddleware,
)


def make_request(task):
    # Create the context used by the middleware
    context = RequestContext(
        user_message="test",
        research_active=False,
        interactive=False,
        task_id=task.task_id,
        turn_id=task.turn_id,
    )

    # Create a small fake runtime
    runtime = SimpleNamespace(
        context=context
    )

    # Create a small fake tool request
    return SimpleNamespace(
        runtime=runtime
    )


def test_active_task_can_run_tool():
    async def run_test():
        runtime = TaskRuntime()
        middleware = TaskCancellationMiddleware(runtime)

        # Start the active task
        task = runtime.start_new_task()

        request = make_request(task)

        tool_called = False

        async def handler(request):
            nonlocal tool_called

            # Simulate a normal tool call
            tool_called = True

            return "tool-result"

        result = await middleware.awrap_tool_call(
            request,
            handler,
        )

        assert tool_called is True
        assert result == "tool-result"

    asyncio.run(run_test())


def test_cancelled_task_does_not_start_tool():
    async def run_test():
        runtime = TaskRuntime()
        middleware = TaskCancellationMiddleware(runtime)

        # Start the first task
        old_task = runtime.start_new_task()

        request = make_request(old_task)

        # Starting a new task cancels the old task
        runtime.start_new_task()

        tool_called = False

        async def handler(request):
            nonlocal tool_called

            # This should never run
            tool_called = True

            return "tool-result"

        with pytest.raises(TaskCancelledError):
            await middleware.awrap_tool_call(
                request,
                handler,
            )

        assert tool_called is False

    asyncio.run(run_test())


def test_task_cancelled_during_tool_rejects_result():
    async def run_test():
        runtime = TaskRuntime()
        middleware = TaskCancellationMiddleware(runtime)

        # Start the original task
        task = runtime.start_new_task()

        request = make_request(task)

        tool_called = False

        async def handler(request):
            nonlocal tool_called

            # The tool starts normally
            tool_called = True

            # A new task arrives while the tool is running
            runtime.start_new_task()

            # This result belongs to the old task
            return "late-tool-result"

        with pytest.raises(TaskCancelledError):
            await middleware.awrap_tool_call(
                request,
                handler,
            )

        assert tool_called is True

    asyncio.run(run_test())