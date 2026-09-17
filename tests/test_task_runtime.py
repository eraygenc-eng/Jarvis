import unittest

from core.planning.task_runtime import TaskRuntime, TaskStatus


class TestTaskRuntime(unittest.TestCase):

    def test_new_task_cancels_previous_task(self):
        # Create the runtime
        runtime = TaskRuntime()

        # Start the first task
        first_task = runtime.start_new_task()

        # Start another task
        second_task = runtime.start_new_task()

        # The old task should be cancelled
        self.assertEqual(
            first_task.status,
            TaskStatus.CANCELLED,
        )

        self.assertTrue(first_task.cancel_requested)

        # The new task should be running
        self.assertEqual(
            second_task.status,
            TaskStatus.RUNNING,
        )

        # The new task should have a new turn
        self.assertEqual(
            second_task.turn_id,
            first_task.turn_id + 1,
        )

        # The new task should be active
        self.assertEqual(
            runtime.active_task.task_id,
            second_task.task_id,
        )

    def test_cancel_active_task(self):
        # Create the runtime
        runtime = TaskRuntime()

        # Start a task
        task = runtime.start_new_task()

        # Cancel the active task
        result = runtime.cancel_active()

        # Cancellation should succeed
        self.assertTrue(result)

        # Task should be cancelled
        self.assertEqual(
            task.status,
            TaskStatus.CANCELLED,
        )

        # Cancellation signal should be set
        self.assertTrue(task.cancel_requested)


    def test_old_task_cannot_publish_result(self):
        # Create the runtime
        runtime = TaskRuntime()

        # Start the first task
        first_task = runtime.start_new_task()

        # Start a new task
        second_task = runtime.start_new_task()

        # Old task result should be rejected
        self.assertFalse(
            runtime.can_publish_result(
                first_task.task_id,
                first_task.turn_id,
            )
        )

        # Current task result should be allowed
        self.assertTrue(
            runtime.can_publish_result(
                second_task.task_id,
                second_task.turn_id,
            )
        )


if __name__ == "__main__":
    unittest.main()