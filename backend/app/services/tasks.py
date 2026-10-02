from uuid import UUID

from app.repositories.tasks import TaskNotFoundError, TaskRepository
from app.schemas.tasks import CheckVocabularyAnswerResponse, SessionTaskPublic
from app.services.users import UserService


class TaskService:
    def __init__(
        self, repository: TaskRepository, users: UserService, engine=None, ispy_guess_generator=None
    ) -> None:
        self.repository = repository
        self.users = users
        self.engine = engine
        self.ispy_guess_generator = ispy_guess_generator

    def get(self, task_id: UUID) -> SessionTaskPublic:
        task = self.repository.get(task_id, self.users.get_current_user().id)
        if task is None:
            raise TaskNotFoundError("Task not found.")
        return SessionTaskPublic.from_internal(task)

    def action(self, task_id, action, request=None):
        from app.repositories.postgres.workflow import PostgresWorkflowRepository

        user = self.users.get_current_user()
        return PostgresWorkflowRepository(
            self.engine, user.id, ispy_guess_generator=self.ispy_guess_generator
        ).task_action(task_id, action, request)

    def check_vocabulary_answer(
        self, task_id, question_id, option_id
    ) -> CheckVocabularyAnswerResponse:
        from app.repositories.postgres.workflow import PostgresWorkflowRepository

        user = self.users.get_current_user()
        return PostgresWorkflowRepository(self.engine, user.id).check_vocabulary_answer(
            task_id, question_id, option_id
        )
