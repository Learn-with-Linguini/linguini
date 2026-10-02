"""Once-daily journal, revision, feedback, and word-highlight schemas."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.schemas.base import ApiModel, EntityModel, NonEmptyText
from app.schemas.enums import (
    JournalRevisionCreator,
    JournalStatus,
    JournalSuggestionStatus,
    JournalSuggestionType,
    WordMatchMethod,
)
from app.schemas.vocabulary import DailyVocabularyItem


class Journal(EntityModel):
    title: Annotated[str, Field(max_length=200)] = "Today's entry"
    selected_words: list[NonEmptyText] = Field(default_factory=list)
    user_id: UUID
    language_profile_id: UUID
    local_date: date
    timezone: str
    status: JournalStatus = JournalStatus.DRAFT
    current_revision_id: UUID | None = None
    audio_media_asset_id: UUID | None = None
    completed_at: AwareDatetime | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_completion(self) -> Journal:
        if self.status is JournalStatus.COMPLETED:
            if self.completed_at is None:
                raise ValueError("completed journals require completedAt")
            if self.current_revision_id is None:
                raise ValueError("completed journals require currentRevisionId")
        return self


class JournalMedia(EntityModel):
    journal_id: UUID
    media_asset_id: UUID
    display_order: Annotated[int, Field(ge=0)]
    caption: Annotated[str, Field(max_length=1000)] | None = None


class JournalRevision(EntityModel):
    journal_id: UUID
    revision_number: Annotated[int, Field(ge=1)]
    content: Annotated[str, Field(min_length=1, max_length=20_000)]
    created_by: JournalRevisionCreator


class JournalSuggestion(EntityModel):
    journal_id: UUID
    base_revision_id: UUID
    suggestion_type: JournalSuggestionType
    start_offset: Annotated[int, Field(ge=0)]
    end_offset: Annotated[int, Field(gt=0)]
    original_text: str
    suggested_text: NonEmptyText
    explanation: NonEmptyText
    status: JournalSuggestionStatus = JournalSuggestionStatus.PENDING

    @model_validator(mode="after")
    def validate_offsets(self) -> JournalSuggestion:
        if self.end_offset <= self.start_offset:
            raise ValueError("endOffset must be greater than startOffset")
        return self


class JournalWordMention(EntityModel):
    journal_revision_id: UUID
    vocabulary_item_id: UUID
    start_offset: Annotated[int, Field(ge=0)]
    end_offset: Annotated[int, Field(gt=0)]
    matched_text: NonEmptyText
    match_method: WordMatchMethod
    source_encounter_id: UUID | None = None

    @model_validator(mode="after")
    def validate_offsets(self) -> JournalWordMention:
        if self.end_offset <= self.start_offset:
            raise ValueError("endOffset must be greater than startOffset")
        return self


class UpsertTodayJournalRequest(ApiModel):
    media_asset_id: UUID | None = None
    language_profile_id: UUID
    title: Annotated[str, Field(max_length=200)] = "Today's entry"
    selected_words: list[NonEmptyText] = Field(default_factory=list)
    content: Annotated[str, Field(min_length=1, max_length=20_000)] | None = None


class UpdateJournalRequest(ApiModel):
    media_asset_id: UUID | None = None
    title: Annotated[str, Field(max_length=200)] | None = None
    selected_words: list[NonEmptyText] | None = None
    content: Annotated[str, Field(min_length=1, max_length=20_000)] | None = None
    audio_media_asset_id: UUID | None = None


class AddJournalMediaRequest(ApiModel):
    media_asset_id: UUID
    display_order: Annotated[int, Field(ge=0)]
    caption: Annotated[str, Field(max_length=1000)] | None = None


class CreateJournalRevisionRequest(ApiModel):
    content: Annotated[str, Field(min_length=1, max_length=20_000)]
    created_by: Literal["user"] = "user"


class GenerateJournalSuggestionsRequest(ApiModel):
    revision_id: UUID


class CompleteJournalRequest(ApiModel):
    current_revision_id: UUID


class JournalPhotoOption(ApiModel):
    media_asset_id: UUID
    image_url: str | None = None
    session_id: UUID
    completed_at: AwareDatetime


class JournalTodayContextResponse(ApiModel):
    local_date: date
    journal: Journal | None = None
    eligible_photos: list[JournalPhotoOption] = Field(default_factory=list)
    learned_words: list[DailyVocabularyItem] = Field(default_factory=list)
    suggested_words: list[NonEmptyText] = Field(default_factory=list)
    can_create: bool


class JournalDetailResponse(ApiModel):
    image_url: str | None = None
    image_urls: dict[UUID, str] = Field(default_factory=dict)
    journal: Journal
    media: list[JournalMedia] = Field(default_factory=list)
    revisions: list[JournalRevision] = Field(default_factory=list)
    suggestions: list[JournalSuggestion] = Field(default_factory=list)
    word_mentions: list[JournalWordMention] = Field(default_factory=list)
