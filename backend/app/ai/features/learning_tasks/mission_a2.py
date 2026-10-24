"""Deterministic A2 mission lessons validated against closed, reviewed fact sets."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.mission import (
    fold,
)
from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.schemas.base import ApiModel, NonEmptyText

type A2Purpose = Literal[
    "chooseSceneMarker",
    "buildSceneFact",
    "chooseSceneDescription",
    "buildSceneDescription",
    "followUpSceneFact",
    "readAttributeClue",
    "buildLocationClue",
    "chooseUniqueTarget",
    "clarifyDistractor",
    "buildTargetSentence",
    "countGroup",
    "buildQuantity",
    "compareGroups",
    "correctRoleplayCount",
    "buildComparison",
    "chooseAssignedObject",
    "choosePossessive",
    "clarifyOwnership",
    "buildBelonging",
    "buildOwnershipDescription",
]

_EXPECTED = {
    "M01": [
        "chooseSceneMarker",
        "buildSceneFact",
        "chooseSceneDescription",
        "buildSceneDescription",
        "followUpSceneFact",
    ],
    "M02": [
        "readAttributeClue",
        "buildLocationClue",
        "chooseUniqueTarget",
        "clarifyDistractor",
        "buildTargetSentence",
    ],
    "M03": [
        "countGroup",
        "buildQuantity",
        "compareGroups",
        "correctRoleplayCount",
        "buildComparison",
    ],
    "M04": [
        "chooseAssignedObject",
        "choosePossessive",
        "buildBelonging",
        "clarifyOwnership",
        "buildOwnershipDescription",
    ],
}
_INTERACTIONS = {
    purpose: "sentenceBuilding"
    if purpose
    in {
        "buildSceneFact",
        "buildSceneDescription",
        "buildLocationClue",
        "buildTargetSentence",
        "buildQuantity",
        "buildComparison",
        "buildBelonging",
        "buildOwnershipDescription",
    }
    else "multipleChoice"
    for purposes in _EXPECTED.values()
    for purpose in purposes
}


class MissionA2Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: A2Purpose
    prompt: NonEmptyText = Field(max_length=300)
    target_language_text: list[NonEmptyText] = Field(default_factory=list)
    option_language: Literal["target", "en"] = "target"
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)] = Field(default_factory=list)
    correct_option_id: Annotated[str, Field(max_length=64)] | None = None
    correct_text: Annotated[str, Field(max_length=300)] | None = None
    token_bank: Annotated[
        list[Annotated[NonEmptyText, Field(max_length=80)]], Field(max_length=60)
    ] = Field(default_factory=list)
    answer_chunks: list[NonEmptyText] = Field(default_factory=list)
    distractor_chunks: list[NonEmptyText] = Field(default_factory=list)
    translation: Annotated[str, Field(max_length=300)] | None = None
    object_key: NonEmptyText | None = None
    section: Annotated[str, Field(max_length=80)]
    marker_object_ids: dict[str, str] | None = None
    group_object_ids: list[str] = Field(default_factory=list)
    roleplay_premise: Annotated[str, Field(max_length=300)] | None = None
    planning_facts: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interaction(self) -> MissionA2Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError("The question interaction does not match its purpose.")
        if self.interaction_type == "multipleChoice":
            ids = [option.option_id for option in self.options]
            if len(ids) < 2 or len(ids) != len(set(ids)):
                raise ValueError("Multiple-choice questions need unique options.")
            labels = [fold(option.label) for option in self.options]
            if len(labels) != len(set(labels)):
                raise ValueError("Multiple-choice questions need unique labels.")
            if self.correct_option_id not in ids or self.correct_text or self.token_bank:
                raise ValueError("Multiple-choice questions need one offered answer.")
            if self.answer_chunks or self.distractor_chunks:
                raise ValueError("Multiple-choice questions cannot include sentence chunks.")
        else:
            if (
                self.options
                or self.correct_option_id
                or not self.correct_text
                or not self.token_bank
                or not self.answer_chunks
            ):
                raise ValueError("Sentence building needs an answer and token bank.")
        return self


class MissionA2Result(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[MissionA2Question], Field(min_length=5, max_length=5)]






























