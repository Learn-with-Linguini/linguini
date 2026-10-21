from uuid import UUID

from app.repositories.language_profiles import LanguageProfileRepository
from app.schemas.users import (
    CreateLanguageProfileRequest,
    LanguageProfile,
    UpdateLanguageProfileRequest,
)
from app.services.users import UserService


class NoActiveLanguageError(Exception):
    pass


class LanguageProfileService:
    def __init__(self, repository: LanguageProfileRepository, users: UserService) -> None:
        self.repository = repository
        self.users = users
        self._profiles: list[LanguageProfile] | None = None

    def list_profiles(self) -> list[LanguageProfile]:
        if self._profiles is None:
            self._profiles = self.repository.list_for_user(self.users.get_current_user().id)
        return self._profiles

    def active_language(self) -> str:
        active = next((row for row in self.list_profiles() if row.is_active), None)
        if active is None:
            raise NoActiveLanguageError("Choose a target language in your profile.")
        return active.target_language_code.lower()

    def create(self, request: CreateLanguageProfileRequest) -> LanguageProfile:
        user = self.users.get_current_user()
        profile = self.repository.create(
            LanguageProfile(user_id=user.id, **request.model_dump(by_alias=False))
        )
        self._profiles = None
        return profile

    def update(self, profile_id: UUID, request: UpdateLanguageProfileRequest) -> LanguageProfile:
        user = self.users.get_current_user()
        profile = self.repository.update(user.id, profile_id, request)
        self._profiles = None
        return profile
