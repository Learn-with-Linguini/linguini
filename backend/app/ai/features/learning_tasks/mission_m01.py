"""M01 A1 mission lesson: identify two photo objects, then describe them.

Task 1 identifies objects: Q1 and Q2 each show one object and ask "is it this?",
answered with a full yes/no chunk; each statement is independently true or names
the other object. Task 2 describes them: Q3 chooses a detail of the first object
(colour preferred) and Q4 builds the second object's description, preferring another
confirmed detail (size, shape, material, pattern or state). The payload holds the two
learner-confirmed object-detail pairs with reviewed target-language forms and the
taught nouns and details that may appear as options. The lesson is built
deterministically and accepted only through ``validate_m01_lesson``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.schemas.base import ApiModel, NonEmptyText

type M01Purpose = Literal["confirmObject", "chooseAttribute", "describeObject"]

IDENTIFY_SECTION = "Task 1 · Identify objects in your photo"
DESCRIBE_SECTION = "Task 2 · Describe them"
CONFIRM_IDS = ("confirm-first", "confirm-second")
_INTERACTIONS = {
    "confirmObject": "multipleChoice",
    "chooseAttribute": "multipleChoice",
    "describeObject": "sentenceBuilding",
}


class M01Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M01Purpose
    section: NonEmptyText = Field(max_length=80)
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=20)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=200)
    attribute_keys: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=1)]
    # Only ``confirmObject``: whether the prompt's statement names the shown object.
    statement_correct: bool | None = None

    @model_validator(mode="after")
    def validate_interaction(self) -> M01Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        if (self.statement_correct is None) != (self.purpose != "confirmObject"):
            raise ValueError("Only yes/no statements record whether the statement is correct.")
        return self


class M01LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    explanation: NonEmptyText = Field(max_length=400)
    questions: Annotated[list[M01Question], Field(min_length=4, max_length=4)]


def capitalised(text: str) -> str:
    return f"{text[:1].upper()}{text[1:]}"


def description(payload: dict[str, Any], pair: dict[str, Any]) -> str:
    """The taught sentence for one pair: ``Es una manzana roja.``, ``C'est une petite tasse.``"""
    article, noun = pair["nounPhrase"].split(" ", 1)
    words = [article, pair["agreedForm"], noun] if pair["before"] else [
        article, noun, pair["agreedForm"],
    ]
    return f"{payload['sentenceStart']} {' '.join(words)}."
















