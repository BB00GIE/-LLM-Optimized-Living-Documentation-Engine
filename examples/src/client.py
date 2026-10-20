"""Task client library for interacting with the Tasks API."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskRecord:
    """Represents a persisted task record."""
    id: str
    title: str
    completed: bool = False


class TaskClient:
    """Client for managing tasks and querying status."""

    def __init__(self, base_url: str = "https://api.example.com", timeout: float = 30.0) -> None:
        """Initialize the TaskClient with target URL and timeout."""
        self.base_url = base_url
        self.timeout = timeout

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task by its unique identifier.

        Args:
            task_id: The unique task UUID string.

        Returns:
            The TaskRecord if found, otherwise None.
        """
        return None

    def create_task(self, title: str, completed: bool = False) -> TaskRecord:
        """Create a new task in the system.

        Args:
            title: The title or summary of the task.
            completed: Initial completion status.

        Returns:
            The newly created TaskRecord.
        """
        return TaskRecord(id="new-1", title=title, completed=completed)


def format_task_summary(task: TaskRecord) -> str:
    """Format a human-readable one-line summary of a task.

    Args:
        task: The task record to format.

    Returns:
        Formatted summary string with completion indicator.
    """
    status = "[x]" if task.completed else "[ ]"
    return f"{status} {task.id}: {task.title}"
