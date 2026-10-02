"""Learning-session workflow schemas."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel, JsonObject
from app.schemas.enums import SessionFailureCode, SessionStatus
from app.schemas.media import AnchorPoint, MediaAsset, SceneObject, SceneObjectRelation
from app.schemas.tasks import SessionProgress, SessionTaskPublic
from app.schemas.translation import SceneTranslationResult
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation


class Session(ApiModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    language_profile_id: UUID
    scene_media_asset_id: UUID
    status: SessionStatus = SessionStatus.CREATED
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    abandoned_at: AwareDatetime | None = None
    session_title: str | None = None
    session_summary: str | None = None
    analysis_draft: JsonObject | None = None
    failure_code: SessionFailureCode | None = None
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> Session:
        if self.status is SessionStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed sessions require completedAt")
        if self.status is SessionStatus.ABANDONED and self.abandoned_at is None:
            raise ValueError("abandoned sessions require abandonedAt")
        if self.completed_at is not None and self.abandoned_at is not None:
            raise ValueError("a session cannot be both completed and abandoned")
        return self


class CreateSessionRequest(ApiModel):
    language_profile_id: UUID
    media_asset_id: UUID
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None


class GenerateSessionPlanRequest(ApiModel):
    desired_vocabulary_count: Annotated[int, Field(ge=1, le=20)] = 5
    include_grammar: bool = True
    include_syntax: bool = True
    include_sentence_building: bool = True
    ispy_round_count: Annotated[int, Field(ge=1, le=20)] = 5


class AddedPracticeObject(ApiModel):
    id: UUID
    label: Annotated[str, Field(min_length=1, max_length=200)]
    x: Annotated[float, Field(ge=0, le=0.99)]
    y: Annotated[float, Field(ge=0, le=0.99)]


class RepositionedPracticeObject(ApiModel):
    id: UUID
    anchor_point: AnchorPoint


class ReviewPracticeRequest(ApiModel):
    scene_title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    relations: Annotated[list[SceneObjectRelation], Field(max_length=100)] = Field(
        default_factory=list
    )
    accepted_object_ids: Annotated[list[UUID], Field(max_length=50)]
    added_objects: Annotated[list[AddedPracticeObject], Field(max_length=20)] = Field(
        default_factory=list
    )
    object_attributes: dict[UUID, dict[str, str]] = Field(default_factory=dict)
    repositioned_objects: Annotated[list[RepositionedPracticeObject], Field(max_length=50)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def unique_selection(self):
        ids = self.accepted_object_ids + [item.id for item in self.added_objects]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Choose at least one object, with no duplicate IDs.")
        selected = set(ids)
        if not set(self.object_attributes) <= selected:
            raise ValueError("Attributes must reference selected objects.")
        moved_ids = [item.id for item in self.repositioned_objects]
        if len(moved_ids) != len(set(moved_ids)):
            raise ValueError("Each object can have only one marker position.")
        if not set(moved_ids) <= selected:
            raise ValueError("Marker positions must reference selected objects.")
        triples = set()
        relation_ids = set()
        for relation in self.relations:
            if (
                not {relation.subject_scene_object_id, relation.reference_scene_object_id}
                <= selected
            ):
                raise ValueError("Relations must reference selected objects.")
            triple = (
                relation.subject_scene_object_id,
                relation.relation.casefold(),
                relation.reference_scene_object_id,
            )
            if triple in triples or relation.id in relation_ids:
                raise ValueError("Duplicate relation.")
            triples.add(triple)
            relation_ids.add(relation.id)
        return self


class SessionDetailResponse(ApiModel):
    analysis_mode: Literal["placeholder"] | None = None
    media_asset: MediaAsset
    scene_id: str | None = None
    title: str
    vocabulary: list[VocabularyItem] = Field(default_factory=list)
    translations: list[VocabularyTranslation] = Field(default_factory=list)
    translation_preview: SceneTranslationResult | None = None
    session: Session
    scene_object_relations: list[SceneObjectRelation] = Field(default_factory=list)
    scene_objects: list[SceneObject] = Field(default_factory=list)
    tasks: list[SessionTaskPublic] = Field(default_factory=list)
    next_task_id: UUID | None = None
    progress: SessionProgress | None = None


class SessionSummaryResponse(ApiModel):
    session: Session
    progress: SessionProgress
    learned_vocabulary_ids: list[UUID] = Field(default_factory=list)
    xp_earned: Annotated[int, Field(ge=0)] = 0
    ispy_correct_count: Annotated[int, Field(ge=0)] = 0
    ispy_attempt_count: Annotated[int, Field(ge=0)] = 0
