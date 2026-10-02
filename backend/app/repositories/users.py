"""User persistence interface and storage errors."""

from typing import Protocol
from uuid import UUID

from app.schemas.users import UpdateUserRequest, User


class UserRepositoryError(Exception):
    """User storage could not be read or validated."""


class UserRepository(Protocol):
    def get_by_id(self, user_id: UUID) -> User | None: ...

    def get_or_create_by_auth_provider(
        self, auth_provider_id: str, email: str | None
    ) -> User: ...

    def update(self, user_id: UUID, request: UpdateUserRequest) -> User | None: ...
