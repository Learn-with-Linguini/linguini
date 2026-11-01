"""M02 A1 mission lesson: find an object, say where it is, ask and answer where it is.

Every question reuses one learner-confirmed relation (subject, position, reference).
Task 1 finds the subject by its photo marker from the confirmed statement, then
chooses the confirmed position. Task 2 builds the where-question and its answer.
The lesson is built deterministically from confirmed objects and relations with
reviewed target-language forms, and accepted only through ``validate_m02_lesson``.
Lessons saved with mission content version 1 keep their persisted questions and
answer key, which grading reads directly.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.schemas.base import ApiModel, NonEmptyText

type M02Purpose = Literal["findObject", "chooseLocation", "askWhere", "answerWhere"]

FIND_SECTION = "Task 1 · Find it in your photo"
ASK_SECTION = "Task 2 · Ask and answer where"
_INTERACTIONS = {
    "findObject": "multipleChoice",
    "chooseLocation": "multipleChoice",
    "askWhere": "sentenceBuilding",
    "answerWhere": "sentenceBuilding",
}


class M02Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M02Purpose
    section: NonEmptyText = Field(max_length=80)
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=20)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=200)
    relation_key: NonEmptyText = Field(max_length=200)
    # Only ``findObject``: option id -> the confirmed scene object behind that marker.
    marker_keys: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_interaction(self) -> M02Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        if (self.marker_keys is None) != (self.purpose != "findObject"):
            raise ValueError("Only marker questions map options to scene objects.")
        return self


class M02LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[M02Question], Field(min_length=4, max_length=4)]












