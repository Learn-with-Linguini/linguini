from typing import Protocol
from uuid import UUID

from app.schemas.progress import StoredProgress
from app.schemas.vocabulary import DailyVocabularyItem


class LearningStorageError(Exception):
    """Learning data could not be read or validated."""


class LearningRepository(Protocol):
    def get_progress(
        self, user_id: UUID, language_code: str | None = None, timezone: str = "UTC"
    ) -> StoredProgress | None: ...

    def list_vocabulary(self, user_id: UUID) -> list[DailyVocabularyItem]: ...
