from dataclasses import dataclass, field
from enum import Enum
from typing import Optional



class StepStatus(str, Enum):
    """Possible states of a task step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str , Enum):
    """Possible states of the whole task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"



@dataclass
class TaskStep:
    """Represents one step inside a task plan."""

    id: int
    description: str
    status: StepStatus = StepStatus.PENDING

    result: Optional[str] = None
    error: Optional[str] = None

    retry_count: int = 0
    max_retries: int = 2


    def start(self) -> None:
        """Mark the step as running."""

        self.status = StepStatus.RUNNING
        self.error = None


    def complete(self, result: Optional[str] = None) -> None:
        """Mark the step as completed and save its result."""

        self.status = StepStatus.COMPLETED
        self.result = result
        self.error = None


    def fail(self, error: str) -> None:
        """Mark the step as failed and record the error."""

        self.status = StepStatus.FAILED
        self.error = error
        self.retry_count += 1


    def can_retry(self) -> bool:
        """Check whether the step can be tried again."""

        return self.retry_count <= self.max_retries


@dataclass
class TaskPlan:
    """Represents the full plan for a user task."""

    goal: str
    steps: list[TaskStep] = field(default_factory=list)

    status: TaskStatus = TaskStatus.PENDING
    current_step_index: int = 0


    def add_step(self, description: str, max_retries: int = 2) -> TaskStep:
        """Add a new step to the task plan."""

        step = TaskStep(
            id=len(self.steps) + 1,
            description=description,
            max_retries=max_retries
        )

        self.steps.append(step)
        return step


    def get_current_step(self) -> Optional[TaskStep]:
        """Return the current step of the plan."""

        if self.current_step_index >= len(self.steps):
            return None

        return self.steps[self.current_step_index]


    def start(self) -> None:
        """Start the task plan."""

        self.status = TaskStatus.RUNNING

        current_step = self.get_current_step()

        if current_step is not None:
            current_step.start()


    def advance(self) -> Optional[TaskStep]:
        """Move the plan to the next step."""

        if self.current_step_index < len(self.steps):
            current_step = self.steps[self.current_step_index]

            if current_step.status != StepStatus.COMPLETED:
                return current_step

            self.current_step_index += 1

        if self.current_step_index >= len(self.steps):
            self.complete()

            return None

        return self.steps[self.current_step_index]



    def complete(self) -> None:
        """Mark the whole task as completed."""

        self.status = TaskStatus.COMPLETED


    def fail(self) -> None:
        """Mark the whole task as failed."""

        self.status = TaskStatus.FAILED