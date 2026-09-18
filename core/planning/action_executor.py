from typing import Any

from core.planning.task_runtime import(
    TaskRun,
    TaskRuntime
)



class ActionExecutor:
    def __init__(self, agent: Any, task_runtime: TaskRuntime):
        # The LangChain agent that does the real work
        self.agent = agent

        # Keeps track of the active task
        self.task_runtime = task_runtime


    async def execute_agent_turn(
            self,
            *,
            task: TaskRun,
            messages: list[dict],
            config: dict,
            context: Any,
    ):
        # Make sure this task is still active
        self.task_runtime.ensure_current(
            task.task_id,
            task.turn_id
        )

        result = await self.agent.ainvoke(
            {
                "messages": messages,
            },
            config=config,
            context=context
        )

        # Checking again
        self.task_runtime.ensure_current(
            task.task_id,
            task.turn_id
        )

        return result