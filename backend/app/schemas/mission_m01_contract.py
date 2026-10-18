"""Multilingual M01 contract input and output models."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, LanguageCode, NonEmptyText
from app.schemas.enums import PartOfSpeech, ProficiencyLevel, SceneRelationType
from app.schemas.tasks import (
    ContentVersion,
    ContractId,
    CorrectionRule,
    MissionId,
    QuestionEvaluation,
    VocabularyChoice,
)

type LinguisticValue = str | bool | int | list[str]
type LinguisticMetadata = dict[ContractId, LinguisticValue]
type SceneAttributeKind = Literal["colour", "size", "shape", "material", "pattern", "state"]
type VocabularyProvenance = Literal["reviewedLexicon", "catalog", "sessionTranslation"]
type ChunkJoin = Literal["space", "none"]
type M01Interaction = Literal["multipleChoice", "markerChoice", "sentenceBuilding"]


def fact_id(kind: Literal["object", "attribute", "relation", "count"], *parts: object) -> str:
    """Build the stable identifier for one confirmed scene fact."""
    expected_parts = {"object": 1, "attribute": 2, "relation": 3, "count": 1}
    if len(parts) != expected_parts[kind]:
        raise ValueError(f"{kind} fact IDs require {expected_parts[kind]} component(s)")
    return ":".join((kind, *(str(part) for part in parts)))


class MissionRef(ApiModel):
    mission_id: Literal["M01"]
    practice_level: ProficiencyLevel
    content_version: ContentVersion


class ConfirmedObject(ApiModel):
    fact_id: NonEmptyText
    scene_object_id: UUID
    label: NonEmptyText
    marker: int | None = None


class ConfirmedAttribute(ApiModel):
    fact_id: NonEmptyText
    object_fact_id: NonEmptyText
    kind: SceneAttributeKind
    value: NonEmptyText


class ConfirmedRelation(ApiModel):
    fact_id: NonEmptyText
    subject_fact_id: NonEmptyText
    reference_fact_id: NonEmptyText
    relation: SceneRelationType


class ConfirmedCount(ApiModel):
    fact_id: NonEmptyText
    object_fact_ids: Annotated[list[NonEmptyText], Field(min_length=1)]
    quantity: Annotated[int, Field(ge=1, le=20)]


class ConfirmedSceneFacts(ApiModel):
    objects: list[ConfirmedObject]
    attributes: list[ConfirmedAttribute]
    relations: list[ConfirmedRelation]
    counted_groups: list[ConfirmedCount]

    @property
    def all_fact_ids(self) -> set[str]:
        return {
            fact.fact_id
            for group in (self.objects, self.attributes, self.relations, self.counted_groups)
            for fact in group
        }

    @model_validator(mode="after")
    def validate_fact_references(self) -> ConfirmedSceneFacts:
        all_ids = [
            fact.fact_id
            for group in (self.objects, self.attributes, self.relations, self.counted_groups)
            for fact in group
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("scene fact IDs must be unique")

        object_ids = {fact.fact_id for fact in self.objects}
        references = [
            *(fact.object_fact_id for fact in self.attributes),
            *(fact.subject_fact_id for fact in self.relations),
            *(fact.reference_fact_id for fact in self.relations),
            *(object_id for fact in self.counted_groups for object_id in fact.object_fact_ids),
        ]
        if unknown := set(references) - object_ids:
            raise ValueError(f"scene facts reference unknown objects: {sorted(unknown)}")
        if any(fact.subject_fact_id == fact.reference_fact_id for fact in self.relations):
            raise ValueError("relation subjects and references must differ")
        return self


class ApprovedTerm(ApiModel):
    term_id: ContractId
    fact_id: NonEmptyText
    source_text: NonEmptyText
    target_text: NonEmptyText
    part_of_speech: PartOfSpeech
    vocabulary_item_id: UUID | None = None
    provenance: VocabularyProvenance
    romanization: str | None = None
    linguistic: LinguisticMetadata = Field(default_factory=dict)


class LearnerContext(ApiModel):
    proficiency_level: ProficiencyLevel
    term_familiarity: dict[str, Annotated[float, Field(ge=0, le=1)]] = Field(
        default_factory=dict
    )
    recent_mission_ids: list[MissionId] = Field(default_factory=list)
    plurals_taught: bool = False


class M01ContractInput(ApiModel):
    contract_version: Literal["m01-multilingual.v1"]
    mission: MissionRef
    target_language: LanguageCode
    instruction_language: LanguageCode
    scene_facts: ConfirmedSceneFacts
    vocabulary: list[ApprovedTerm]
    reviewed_examples: list[NonEmptyText] = Field(default_factory=list)
    learner: LearnerContext

    @model_validator(mode="after")
    def validate_structure(self) -> M01ContractInput:
        if self.learner.proficiency_level != self.mission.practice_level:
            raise ValueError("learner proficiency must match mission practice level")
        unknown_facts = {term.fact_id for term in self.vocabulary} - self.scene_facts.all_fact_ids
        if unknown_facts:
            raise ValueError(f"vocabulary references unknown scene facts: {sorted(unknown_facts)}")
        return self


class PreparationCard(ApiModel):
    card_id: ContractId
    text: NonEmptyText
    translation: NonEmptyText | None = None
    fact_ids: list[NonEmptyText]
    audio: bool = True


class SentenceChunk(ApiModel):
    chunk_id: ContractId
    text: NonEmptyText
    join: ChunkJoin


class Feedback(ApiModel):
    correct: str | None = None
    corrections: list[CorrectionRule]


class ContractQuestion(ApiModel):
    question_id: ContractId
    target_ids: Annotated[list[ContractId], Field(min_length=1)]
    section: NonEmptyText | None = None
    prompt: NonEmptyText
    prompt_translation: str | None = None
    instruction: str | None = None
    interaction: M01Interaction
    options: list[VocabularyChoice]
    marker_fact_ids: dict[NonEmptyText, NonEmptyText] | None = None
    chunks: list[SentenceChunk]
    fact_ids: list[NonEmptyText]
    feedback: Feedback


class Answer(ApiModel):
    correct_option_id: NonEmptyText | None = None
    chunk_ids: list[ContractId] = Field(default_factory=list)


class PrivateEvaluation(ApiModel):
    answers: dict[ContractId, Answer]
    evaluations: list[QuestionEvaluation]


class M01ContractOutput(ApiModel):
    contract_version: Literal["m01-multilingual.v1"]
    mission: MissionRef
    target_language: LanguageCode
    instruction_language: LanguageCode
    objective_id: ContractId
    title: NonEmptyText
    explanation: str | None = None
    preparation: list[PreparationCard]
    questions: list[ContractQuestion]
    private: PrivateEvaluation

    def public_dump(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude={"private"})


class GeneratedMarkerOption(ApiModel):
    option_id: ContractId
    fact_id: NonEmptyText


class GeneratedQuestion(ApiModel):
    question_id: ContractId
    target_ids: Annotated[list[ContractId], Field(min_length=1)]
    section: NonEmptyText | None = None
    prompt: NonEmptyText
    prompt_translation: str | None = None
    instruction: str | None = None
    interaction: M01Interaction
    options: list[VocabularyChoice]
    marker_options: list[GeneratedMarkerOption]
    chunks: list[SentenceChunk]
    fact_ids: list[NonEmptyText]
    answer: Answer
    feedback: Feedback


class M01GeneratedLesson(ApiModel):
    """List-shaped model response, excluding server-derived private evaluations."""

    title: NonEmptyText
    explanation: str | None = None
    preparation: list[PreparationCard]
    questions: list[GeneratedQuestion]
