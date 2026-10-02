"""Current-user lookup, independent of HTTP and storage format."""

from uuid import UUID

from app.repositories.users import UserRepository
from app.schemas.users import UpdateUserRequest, User


class UserNotFoundError(Exception):
    """The authenticated user does not exist."""


class UserService:
    def __init__(self, repository: UserRepository, user_id: UUID) -> None:
        self.repository = repository
        self.user_id = user_id
        self._current_user: User | None = None

    def get_current_user(self) -> User:
        if self._current_user is None:
            user = self.repository.get_by_id(self.user_id)
            if user is None:
                raise UserNotFoundError("The authenticated user was not found.")
            self._current_user = user
        return self._current_user

    def update_current_user(self, request: UpdateUserRequest) -> User:
        user = self.repository.update(self.user_id, request)
        if user is None:
            raise UserNotFoundError("The authenticated user was not found.")
        self._current_user = user
        return user
