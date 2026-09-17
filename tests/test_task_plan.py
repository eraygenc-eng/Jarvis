from core.planning.task_plan import (
    StepStatus,
    TaskStatus,
    TaskPlan,
)


def test_task_plan_flow():
    """Test the basic task plan lifecycle."""

    plan = TaskPlan(goal="Open the latest PDF")

    step1 = plan.add_step("Open Downloads folder")
    step2 = plan.add_step("Find the latest PDF")
    step3 = plan.add_step("Open the PDF")

    assert len(plan.steps) == 3
    assert plan.status == TaskStatus.PENDING
    assert plan.current_step_index == 0

    plan.start()

    assert plan.status == TaskStatus.RUNNING
    assert plan.get_current_step() == step1

    step1.start()
    assert step1.status == StepStatus.RUNNING

    step1.complete("Downloads folder opened")
    assert step1.status == StepStatus.COMPLETED
    assert step1.result == "Downloads folder opened"

    next_step = plan.advance()

    assert next_step == step2
    assert plan.current_step_index == 1

    step2.start()
    step2.complete("Latest PDF found")

    next_step = plan.advance()

    assert next_step == step3
    assert plan.current_step_index == 2

    step3.start()
    step3.complete("PDF opened")

    next_step = plan.advance()

    assert next_step is None
    assert plan.status == TaskStatus.COMPLETED



def test_advance_does_not_skip_incomplete_step():
    """Do not move forward while the current step is incomplete."""

    plan = TaskPlan(goal="Test incomplete step")

    step1 = plan.add_step("First step")
    step2 = plan.add_step("Second step")

    plan.start()

    step1.start()

    returned_step = plan.advance()

    assert returned_step == step1
    assert plan.current_step_index == 0
    assert plan.get_current_step() == step1
    assert step2.status == StepStatus.PENDING