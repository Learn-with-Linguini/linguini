from uuid import UUID

from app.repositories.tasks import TaskNotFoundError, TaskRepository
from app.schemas.tasks import (
    CheckVocabularyAnswerResponse,
    LatestAttemptResponse,
    LatestClueAttempt,
    SessionTaskPublic,
)
from app.services.users import UserService


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        users: UserService,
        engine=None,
        ispy_guess_generator=None,
        ai=None,
    ) -> None:
        self.repository = repository
        self.users = users
        self.engine = engine
        self.ispy_guess_generator = ispy_guess_generator
        self.ai = ai

    def get(self, task_id: UUID) -> SessionTaskPublic:
        user_id = self.users.get_current_user().id
        task = self.repository.get(task_id, user_id)
        if task is None:
            raise TaskNotFoundError("Task not found.")
        mode = self.repository.get_session_mode(task.session_id, user_id)
        if mode is None:
            raise TaskNotFoundError("Task not found.")
        return SessionTaskPublic.from_internal(task, mode=mode)

    def latest_attempt(self, task_id: UUID) -> LatestAttemptResponse:
        """Restore an answered I-Spy round or mission lesson; other kinds have nothing here."""
        user_id = self.users.get_current_user().id
        task = self.repository.get(task_id, user_id)
        if task is None:
            raise TaskNotFoundError("Task not found.")
        grouped = task.kind == "grammarLesson" and bool(
            getattr(task.public_content, "mission_id", None)
        )
        if task.kind not in {"reflection", "ispyRound"} and not grouped:
            return LatestAttemptResponse()
        attempts = self.repository.list_attempts(task_id, user_id)
        return LatestAttemptResponse(
            attempt=LatestClueAttempt.from_attempt(attempts[-1], grouped) if attempts else None
        )

    def action(self, task_id, action, request=None):
        from app.repositories.postgres.workflow import PostgresWorkflowRepository

        user = self.users.get_current_user()
        return PostgresWorkflowRepository(
            self.engine, user.id, ispy_guess_generator=self.ispy_guess_generator, ai=self.ai
        ).task_action(task_id, action, request)

    def confirm_guess(self, task_id, attempt_id):
        from app.repositories.postgres.workflow import PostgresWorkflowRepository

        user = self.users.get_current_user()
        return PostgresWorkflowRepository(self.engine, user.id).confirm_guess(task_id, attempt_id)

    def check_vocabulary_answer(
        self, task_id, question_id, option_id
    ) -> CheckVocabularyAnswerResponse:
        from app.repositories.postgres.workflow import PostgresWorkflowRepository

        user = self.users.get_current_user()
        return PostgresWorkflowRepository(self.engine, user.id).check_vocabulary_answer(
            task_id, question_id, option_id
        )
