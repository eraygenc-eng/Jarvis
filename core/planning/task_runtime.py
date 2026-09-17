from enum import Enum
from dataclasses import dataclass, field
from threading import Event, RLock # For cancelling (Event)
from uuid import uuid4


class TaskStatus(str, Enum):
    PENDING = "pending"

    RUNNING = "running"

    COMPLETED = "completed"

    CANCELLED = "cancelled"

    FAILED = "failed"


class TaskCancelledError(RuntimeError):
    pass


@dataclass
class TaskRun:
    # Unique id for this task
    task_id: str = field(default_factory=lambda: uuid4().hex)

    # splits user requests
    turn_id: int = 0

    # Current task status
    status: TaskStatus = TaskStatus.PENDING

    _cancel_event: Event = field(
        default_factory=Event,
        repr=False
    )

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()


    def start(self) -> None:
        if self.cancel_requested:
            self.status = TaskStatus.CANCELLED
            return

        if self.status != TaskStatus.PENDING:
            return

        self.status = TaskStatus.RUNNING


    def cancel(self) -> None:
        if self.status in {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        }:
            return

        # Send cancellation signal
        self._cancel_event.set()

        # Update task status
        self.status = TaskStatus.CANCELLED


    def complete(self) -> None:
        if self.cancel_requested:
            self.status = TaskStatus.CANCELLED
            return

        # Ignore already finished tasks
        if self.status in {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        }:
            return

        # Mark as a completed
        self.status = TaskStatus.COMPLETED


    def fail(self) -> None:
        if self.cancel_requested:
            self.status = TaskStatus.CANCELLED
            return

        # Ignore already finished tasks
        if self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }:
            return

        # Mark as a failed
        self.status = TaskStatus.FAILED


    def ensure_active(self) -> None:
        if self.cancel_requested:
            raise TaskCancelledError(f"Task {self.task_id} was cancelled.")

        if self.status == TaskStatus.CANCELLED:
            raise TaskCancelledError(f"Task {self.task_id} was cancelled.")


class TaskRuntime:
    def __init__(self) -> None:
        # Protect shared runtime state
        self._lock = RLock()

        # Count user turns
        self._turn_counter = 0

        # Store the current task id
        self._active_task_id: str | None = None

        # store all task runs
        self._tasks: dict[str, TaskRun] = {}


    @property
    def active_task(self) -> TaskRun | None:
        with self._lock:
            if self._active_task_id is None:
                return None

            return self._tasks.get(self._active_task_id)


    def start_new_task(self) -> TaskRun:
        with self._lock:
            previous_task = self.active_task

            if previous_task is not None:
                previous_task.cancel()

            self._turn_counter += 1

            # Create a new task
            task = TaskRun(turn_id=self._turn_counter)

            task.start()

            # Store the task
            self._tasks[task.task_id] = task

            # Make it active
            self._active_task_id = task.task_id

            return task


    def cancel_active(self) -> bool:
        with self._lock:
            task = self.active_task

            if task is None:
                return False

            # Ignore already finished tasks
            if task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
                TaskStatus.FAILED,
            }:
                return False

            task.cancel()

            return True


    def complete_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                return False

            # Mark as a completed
            task.complete()

            return True



    def fail_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                return False

            # Mark as a failed
            task.fail()

            return True



    def ensure_current(self, task_id: str, turn_id: int) -> TaskRun:
        with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                raise TaskCancelledError(f"Unknown task: {task_id}")

            # Task belongs to an old turn
            if task.turn_id != turn_id:
                raise TaskCancelledError(f"Stale turn for task {task_id}.")

            # Task is no longer active
            if self._active_task_id != task_id:
                raise TaskCancelledError(f"Task {task_id} is no longer active.")

            # Task was cancelled
            task.ensure_active()

            return task


    def can_publish_result(self, task_id: str, turn_id: int) -> bool:
        # Check if this task is still current
        try:
            task = self.ensure_current(
                task_id=task_id,
                turn_id=turn_id
            )
        except TaskCancelledError:
            return False

        return task.status == TaskStatus.RUNNING