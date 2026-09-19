from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest

from core.context import RequestContext
from core.planning.task_runtime import TaskRuntime



class TaskCancellationMiddleware(AgentMiddleware):
    def __init__(self, task_runtime: TaskRuntime) -> None:
        # Keep the shared task runtime
        self.task_runtime = task_runtime


    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        # Get the current request context
        context = request.runtime.context

        if not isinstance(context, RequestContext):
            return await handler(request)

        # Skip cancellation checks for untracked calls
        if context.task_id is None or context.turn_id is None:
            return await handler(request)

        # Check before running the tool
        self.task_runtime.ensure_current(
            context.task_id,
            context.turn_id
        )

        # Run the real tool
        result = await handler(request)

        # checking after tool finished
        self.task_runtime.ensure_current(
            context.task_id,
            context.turn_id
        )

        return result