from typing import Protocol
from uuid import UUID

from app.schemas.users import LanguageProfile, UpdateLanguageProfileRequest


class LanguageProfileStorageError(Exception):
    pass


class LanguageProfileNotFoundError(Exception):
    pass


class LanguageProfileConflictError(Exception):
    pass


class LanguageProfileRepository(Protocol):
    def list_for_user(self, user_id: UUID) -> list[LanguageProfile]: ...

    def create(self, profile: LanguageProfile) -> LanguageProfile: ...

    def update(
        self, user_id: UUID, profile_id: UUID, request: UpdateLanguageProfileRequest
    ) -> LanguageProfile: ...
