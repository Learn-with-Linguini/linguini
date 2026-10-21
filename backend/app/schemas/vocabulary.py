"""Vocabulary catalog, encounter, and learner-progress schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel, EntityModel, LanguageCode, UnitScore, utc_now
from app.schemas.enums import (
    PartOfSpeech,
    ProficiencyLevel,
    VocabularyEncounterOutcome,
    VocabularyEncounterType,
    VocabularyLearningStatus,
)


class VocabularyItem(EntityModel):
    language_code: LanguageCode
    lemma: Annotated[str, Field(min_length=1, max_length=200)]
    display_text: Annotated[str, Field(min_length=1, max_length=200)]
    part_of_speech: PartOfSpeech
    gender: Annotated[str, Field(max_length=50)] | None = None
    plural_form: Annotated[str, Field(max_length=200)] | None = None
    phonetic_text: Annotated[str, Field(max_length=300)] | None = None
    pronunciation_audio_asset_id: UUID | None = None
    example_sentence: Annotated[str, Field(max_length=1000)] | None = None
    difficulty_level: ProficiencyLevel | None = None


class VocabularyTranslation(EntityModel):
    vocabulary_item_id: UUID
    source_language_code: LanguageCode
    translated_text: Annotated[str, Field(min_length=1, max_length=300)]
    short_definition: Annotated[str, Field(max_length=1000)] | None = None


class UserVocabularyProgress(EntityModel):
    user_id: UUID
    vocabulary_item_id: UUID
    status: VocabularyLearningStatus = VocabularyLearningStatus.NEW
    exposure_count: Annotated[int, Field(ge=0)] = 0
    correct_attempt_count: Annotated[int, Field(ge=0)] = 0
    mastery_score: UnitScore = Decimal("0")
    first_learned_at: AwareDatetime | None = None
    last_practised_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def correct_attempts_cannot_exceed_exposures(self) -> UserVocabularyProgress:
        if self.correct_attempt_count > self.exposure_count:
            raise ValueError("correctAttemptCount cannot exceed exposureCount")
        return self


class VocabularyEncounter(EntityModel):
    user_id: UUID
    vocabulary_item_id: UUID
    session_id: UUID
    session_task_id: UUID
    encounter_type: VocabularyEncounterType
    outcome: VocabularyEncounterOutcome
    occurred_at: AwareDatetime = Field(default_factory=utc_now)


class VocabularyScene(ApiModel):
    media_asset_id: UUID
    title: str
    scene_id: str | None = None


class DailyVocabularyItem(ApiModel):
    # Optional presentation metadata for the originating demo scene.
    scene_id: str | None = None
    topic: str | None = None
    vocabulary: VocabularyItem
    translation: VocabularyTranslation | None = None
    progress: UserVocabularyProgress | None = None
    encounter_ids: list[UUID] = Field(default_factory=list)
    scenes: list[VocabularyScene] = Field(default_factory=list)


class DailyVocabularyResponse(ApiModel):
    local_date: date
    words: list[DailyVocabularyItem] = Field(default_factory=list)
