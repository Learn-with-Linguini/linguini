"""One session workflow for curated and uploaded media."""

from app.repositories.practice import PracticeConflictError
from app.services.language_profiles import NoActiveLanguageError


class PracticeService:
    def __init__(self, repository, users, profiles):
        self.repository, self.users, self.profiles = repository, users, profiles

    def _profile(self):
        profile = next((p for p in self.profiles.list_profiles() if p.is_active), None)
        if profile is None:
            raise NoActiveLanguageError("Choose a target language in your profile.")
        return profile

    def get(self, session_id):
        return self.repository.get(session_id, self._profile().id)

    def active(self):
        return self.repository.active(self._profile().id)

    def create(self, request):
        if request.language_profile_id != self._profile().id:
            raise PracticeConflictError("Select the active language profile.")
        return self.repository.create(request)

    def analyze(self, session_id):
        return self.repository.analyze(session_id, self._profile().id)

    def complete(self, session_id):
        return self.repository.finish(session_id, self._profile().id)

    def check_word(self, session_id, label):
        return self.repository.check_word(session_id, self._profile().id, label)

    def review(self, session_id, request):
        return self.repository.review(session_id, self._profile().id, request)

    def abandon(self, session_id):
        return self.repository.finish(session_id, self._profile().id, abandon=True)

    def summary(self, session_id):
        return self.repository.summary(session_id, self._profile().id)
