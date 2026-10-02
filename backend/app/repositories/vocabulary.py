"""Vocabulary persistence contract shared by practice and journal services."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.schemas.vocabulary import VocabularyEncounter


class VocabularyRepository(Protocol):
    def record_encounter(self, encounter: VocabularyEncounter) -> VocabularyEncounter: ...

    def record_journal_usage(
        self,
        *,
        user_id: UUID,
        language_profile_id: UUID,
        journal_id: UUID,
        words: list[str],
        occurred_at: datetime,
    ) -> list[UUID]: ...
