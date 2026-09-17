import asyncio

from core.planning.planner import (
    PlannedStep,
    PlannerOutput,
    TaskPlanner,
)
from core.planning.task_plan import (
    StepStatus,
    TaskStatus,
)


class FakeStructuredLLM:
    """Returns a fixed structured planner response."""

    async def ainvoke(self, messages):
        # Return a predictable planner output
        return PlannerOutput(
            goal="Open the latest PDF in Downloads",
            steps=[
                PlannedStep(
                    description="Open the Downloads folder"
                ),
                PlannedStep(
                    description="Find the most recent PDF"
                ),
                PlannedStep(
                    description="Open the PDF"
                ),
            ],
        )


class FakeLLM:
    """Acts like an LLM that supports structured output."""

    def with_structured_output(self, schema):
        # Return our fake structured model
        return FakeStructuredLLM()



def test_task_planner_creates_task_plan():
    """Convert structured LLM output into a TaskPlan."""

    # Create the planner with a fake model
    planner = TaskPlanner(FakeLLM())

    # Create a plan from a user request
    plan = asyncio.run(
        planner.plan(
            "Open the latest PDF in Downloads"
        )
    )

    # Check the main task information
    assert plan.goal == "Open the latest PDF in Downloads"
    assert plan.status == TaskStatus.PENDING

    # Check the generated steps
    assert len(plan.steps) == 3

    assert plan.steps[0].id == 1
    assert plan.steps[0].description == "Open the Downloads folder"

    assert plan.steps[1].id == 2
    assert plan.steps[1].description == "Find the most recent PDF"

    assert plan.steps[2].id == 3
    assert plan.steps[2].description == "Open the PDF"

    # New steps must always start as pending
    for step in plan.steps:
        assert step.status == StepStatus.PENDING



def test_task_planner_rejects_empty_request():
    """Reject empty user requests."""

    planner = TaskPlanner(FakeLLM())

    try:
        asyncio.run(planner.plan("   "))
        assert False, "Expected ValueError for empty request"
    except ValueError as error:
        assert str(error) == "User request cannot be empty."


class EmptyStepsStructuredLLM:
    """Returns a plan with no usable steps."""

    async def ainvoke(self, messages):
        # Return an invalid empty plan
        return PlannerOutput(
            goal="Do something",
            steps=[],
        )


class EmptyStepsLLM:
    """Provides the empty structured response."""

    def with_structured_output(self, schema):
        # Return the fake empty planner
        return EmptyStepsStructuredLLM()



def test_task_planner_rejects_empty_steps():
    """Reject planner outputs that contain no steps."""

    planner = TaskPlanner(EmptyStepsLLM())

    try:
        asyncio.run(
            planner.plan("Do something")
        )
        assert False, "Expected ValueError for empty steps"
    except ValueError as error:
        assert str(error) == "Planner returned no usable steps."