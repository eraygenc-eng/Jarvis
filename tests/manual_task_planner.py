import asyncio

from core.llm.factory import create_llm
from core.planning.planner import TaskPlanner


async def main():
    # Create Jarvis' configured LLM
    llm = create_llm()

    # Give the real LangChain model to the planner
    planner = TaskPlanner(llm.get_model())

    # Create a real task plan
    plan = await planner.plan(
        "Downloads klasöründeki en son PDF dosyasını aç."
    )

    # Show the generated goal
    print("\nGOAL:")
    print(plan.goal)

    # Show every generated step
    print("\nSTEPS:")

    for step in plan.steps:
        print(
            f"{step.id}. {step.description} "
            f"[{step.status.value}]"
        )


if __name__ == "__main__":
    asyncio.run(main())