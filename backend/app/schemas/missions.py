"""Versioned mission definitions: what a mission teaches, accepts and expects."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, LanguageCode, NonEmptyText
from app.schemas.enums import MediaSource, ProficiencyLevel, SceneRelationType, TaskKind
from app.schemas.tasks import (
    ClueFrameId,
    ContentVersion,
    ContractId,
    EvidenceType,
    MissionId,
    QuestionEvaluation,
    SupportKind,
)


def _unique(values, message):
    if len(values) != len(set(values)):
        raise ValueError(message)


class PhotoRequirements(ApiModel):
    """What a reviewed photo must contain before the mission can use it."""

    media_sources: Annotated[list[MediaSource], Field(min_length=1)]
    min_confirmed_objects: Annotated[int, Field(ge=1)]
    min_describable_objects: Annotated[int, Field(ge=1)]
    describable_by: Annotated[list[Literal["colour", "relation"]], Field(min_length=1)]
    relations: list[SceneRelationType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_requirements(self) -> PhotoRequirements:
        if self.min_describable_objects > self.min_confirmed_objects:
            raise ValueError("describable objects cannot exceed confirmed objects")
        if ("relation" in self.describable_by) != bool(self.relations):
            raise ValueError("relations are listed exactly when objects are describable by them")
        return self


class MissionTarget(ApiModel):
    target_id: ContractId
    summary: NonEmptyText
    evidence_types: Annotated[list[EvidenceType], Field(min_length=1)]


class LearningObjective(ApiModel):
    objective_id: ContractId
    can_do: NonEmptyText
    targets: Annotated[list[MissionTarget], Field(min_length=1)]


class LanguagePattern(ApiModel):
    """A permitted sentence pattern; ``clueFrameId`` names the existing frame that teaches it."""

    pattern_id: ContractId
    target_id: ContractId
    structure: NonEmptyText
    clue_frame_id: ClueFrameId | None = None
    examples: dict[LanguageCode, Annotated[list[NonEmptyText], Field(min_length=1)]]


class SupportRule(ApiModel):
    support: SupportKind
    availability: Literal["always", "onRequest"]
    counts_as_assistance: bool


class TeachingRequirements(ApiModel):
    task_sequence: Annotated[list[TaskKind], Field(min_length=1)]
    teach_before_assessment: list[ContractId] = Field(default_factory=list)
    max_new_words: Annotated[int, Field(ge=1, le=12)]
    supports: list[SupportRule] = Field(default_factory=list)


class EvaluationCriterion(ApiModel):
    criterion_id: ContractId
    target_id: ContractId
    description: NonEmptyText
    evidence_types: Annotated[list[EvidenceType], Field(min_length=1)]


class ExpectedPerformance(ApiModel):
    """``requiredTargetGroups``: each group needs a correct outcome for one of its targets."""

    min_assessed_questions: Annotated[int, Field(ge=1)]
    min_correct_ratio: Annotated[float, Field(ge=0, le=1)]
    min_independent_correct: Annotated[int, Field(ge=0)]
    required_target_groups: list[Annotated[list[ContractId], Field(min_length=1)]] = Field(
        default_factory=list
    )


class MissionDefinition(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    title: NonEmptyText
    photo_requirements: PhotoRequirements
    objective: LearningObjective
    language_patterns: Annotated[list[LanguagePattern], Field(min_length=1)]
    teaching: TeachingRequirements
    evaluation_criteria: Annotated[list[EvaluationCriterion], Field(min_length=1)]
    expected_performance: ExpectedPerformance

    @model_validator(mode="after")
    def validate_references(self) -> MissionDefinition:
        targets = self.targets
        _unique([item.target_id for item in self.objective.targets], "targetIds cannot repeat")
        _unique([item.pattern_id for item in self.language_patterns], "patternIds cannot repeat")
        _unique(
            [item.criterion_id for item in self.evaluation_criteria], "criterionIds cannot repeat"
        )
        _unique([item.support for item in self.teaching.supports], "supports cannot repeat")
        referenced = [
            *(item.target_id for item in self.language_patterns),
            *(item.target_id for item in self.evaluation_criteria),
            *self.teaching.teach_before_assessment,
            *(target for group in self.expected_performance.required_target_groups
              for target in group),
        ]
        if unknown := sorted(set(referenced) - set(targets)):
            raise ValueError(f"unknown targetIds: {', '.join(unknown)}")
        for criterion in self.evaluation_criteria:
            allowed = set(targets[criterion.target_id].evidence_types)
            if not set(criterion.evidence_types) <= allowed:
                raise ValueError(f"{criterion.criterion_id} uses evidence its target does not")
        return self

    @property
    def key(self) -> tuple[str, ProficiencyLevel, int]:
        return self.mission_id, self.practice_level, self.content_version

    @property
    def targets(self) -> dict[str, MissionTarget]:
        return {item.target_id: item for item in self.objective.targets}

    def counts_as_assistance(self, support: SupportKind) -> bool:
        """Supports without a rule count as assistance, so recall is never overstated."""
        rule = next((item for item in self.teaching.supports if item.support == support), None)
        return rule is None or rule.counts_as_assistance

    def check_evaluation(self, evaluation: QuestionEvaluation) -> None:
        if evaluation.objective_id != self.objective.objective_id:
            raise ValueError("question evaluation names another objective")
        targets = self.targets
        if unknown := set(evaluation.target_ids) - set(targets):
            raise ValueError(f"question evaluation names unknown targets: {sorted(unknown)}")
        if any(
            evaluation.evidence_type not in targets[target].evidence_types
            for target in evaluation.target_ids
        ):
            raise ValueError("question evaluation uses evidence its targets do not accept")
        criteria = {item.criterion_id: item for item in self.evaluation_criteria}
        for criterion_id in evaluation.rubric_criterion_ids:
            criterion = criteria.get(criterion_id)
            if criterion is None or criterion.target_id not in evaluation.target_ids:
                raise ValueError("rubric criteria must belong to the assessed targets")
