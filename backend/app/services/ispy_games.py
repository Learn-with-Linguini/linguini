"""Standalone I-Spy games for the active language profile."""

from app.repositories.practice import PracticeConflictError
from app.services.language_profiles import NoActiveLanguageError


class ISpyGameService:
    def __init__(self, repository, profiles):
        self.repository, self.profiles = repository, profiles

    def _profile(self):
        profile = next((p for p in self.profiles.list_profiles() if p.is_active), None)
        if profile is None:
            raise NoActiveLanguageError("Choose a target language in your profile.")
        return profile

    def photos(self, cursor=None):
        self._profile()
        return self.repository.photos(cursor)

    def active(self):
        return self.repository.active(self._profile().id)

    def start(self, request):
        if request.language_profile_id != self._profile().id:
            raise PracticeConflictError("Select the active language profile.")
        return self.repository.start(request)
