from typing import Protocol
from uuid import UUID

from app.schemas.tasks import SessionTask, TaskAttempt, TaskHint


class TaskStorageError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class TaskConflictError(Exception):
    pass


class TaskRepository(Protocol):
    def get(self, task_id: UUID, user_id: UUID) -> SessionTask | None: ...
    def list_for_session(self, session_id: UUID, user_id: UUID) -> list[SessionTask]: ...
    def list_attempts(self, task_id: UUID, user_id: UUID) -> list[TaskAttempt]: ...
    def list_hints(self, task_id: UUID, user_id: UUID) -> list[TaskHint]: ...
    def create_task(self, task: SessionTask, user_id: UUID) -> SessionTask: ...
    def create_attempt(self, attempt: TaskAttempt, user_id: UUID) -> TaskAttempt: ...
    def create_hint(self, hint: TaskHint, user_id: UUID) -> TaskHint: ...
