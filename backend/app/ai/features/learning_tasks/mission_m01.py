"""M01 A1 mission lesson: identify two photo objects and describe each by its colour.

The payload holds the two selected learner-confirmed object-colour pairs with their
reviewed target-language forms. The lesson is built deterministically and accepted
only through ``validate_m01_lesson``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.mission import (
    MissionGeneration,
    checked_answer,
    fold,
    tokens,
    unique_question_ids,
)
from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel, NonEmptyText

M01_PROMPT_VERSION = "learning-tasks.m01-a1.v2"
M01_SCHEMA_VERSION = "learning-tasks-m01-result.v2"
M01_VALIDATOR_VERSION = "learning-tasks-m01-validator.v2"
DESCRIBE_PROMPT = "Describe this object."

type M01Purpose = Literal["identifyObject", "describeObject"]

_INTERACTIONS = {"identifyObject": "multipleChoice", "describeObject": "sentenceBuilding"}
_ORDER = ["identifyObject", "describeObject", "identifyObject", "describeObject"]


class M01Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M01Purpose
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=20)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=200)
    attribute_keys: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=1)]

    @model_validator(mode="after")
    def validate_interaction(self) -> M01Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        return self


class M01LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    explanation: NonEmptyText = Field(max_length=400)
    questions: Annotated[list[M01Question], Field(min_length=4, max_length=4)]


def _capitalised(text: str) -> str:
    return f"{text[:1].upper()}{text[1:]}"


def description(payload: dict[str, Any], pair: dict[str, Any]) -> str:
    """The taught sentence for one pair, e.g. ``Es una manzana roja.``"""
    return f"{payload['sentenceStart']} {pair['nounPhrase']} {pair['agreedForm']}."


def validate_m01_lesson(payload: dict[str, Any], result: M01LessonResult) -> None:
    """Four questions on the two selected pairs: identify then describe each object."""
    pairs = payload["pairs"]
    questions = result.questions
    unique_question_ids(questions)
    if len(pairs) != 2 or fold(pairs[0]["source"]) == fold(pairs[1]["source"]):
        raise LearningTaskGenerationError("The lesson needs two different confirmed objects.")
    if [question.purpose for question in questions] != _ORDER:
        raise LearningTaskGenerationError("Each object is identified, then described.")
    for question, pair in zip(questions, [pairs[0], pairs[0], pairs[1], pairs[1]], strict=True):
        if question.object_key != pair["key"]:
            raise LearningTaskGenerationError("Questions follow the selected objects in order.")
        correct = checked_answer(question)
        if question.purpose == "identifyObject":
            if question.attribute_keys or correct != fold(pair["nounPhrase"]):
                raise LearningTaskGenerationError("Identification answers name the object.")
            nouns = {fold(option.label) for option in question.options}
            if fold(pairs[1 - pairs.index(pair)]["nounPhrase"]) not in nouns:
                raise LearningTaskGenerationError("The other selected object is a distractor.")
        elif question.attribute_keys != [pair["colourKey"]] or correct != fold(
            description(payload, pair)
        ):
            raise LearningTaskGenerationError(
                "Descriptions use the taught pattern with the object's confirmed colour."
            )


def fallback_m01_lesson(payload: dict[str, Any]) -> M01LessonResult:
    """The deterministic M01 lesson; it passes the same validator."""
    pairs = payload["pairs"]
    if len(pairs) != 2:
        raise LearningTaskGenerationError("The lesson needs two confirmed object-colour pairs.")
    questions = []
    for number, pair in enumerate(pairs, 1):
        labels = [pair["nounPhrase"], *payload["distractors"][pair["key"]]][:4]
        ordered = sorted(labels, key=fold)
        options = [
            dict(option_id=f"identify-{number}-{index}", label=_capitalised(label))
            for index, label in enumerate(ordered, 1)
        ]
        sentence = description(payload, pair)
        questions += [
            dict(
                question_id=f"identify-object-{number}",
                purpose="identifyObject",
                prompt=payload["identifyPrompt"],
                interaction_type="multipleChoice",
                options=options,
                correct_option_id=options[ordered.index(pair["nounPhrase"])]["option_id"],
                correct_text=None, token_bank=[], translation=None,
                object_key=pair["key"], attribute_keys=[],
            ),
            dict(
                question_id=f"describe-object-{number}",
                purpose="describeObject",
                prompt=DESCRIBE_PROMPT,
                interaction_type="sentenceBuilding",
                options=[], correct_option_id=None,
                correct_text=sentence,
                token_bank=sorted(tokens(sentence), key=fold),
                translation=f"It's a {pair['colourSource']} {pair['source']}.",
                object_key=pair["key"], attribute_keys=[pair["colourKey"]],
            ),
        ]
    example = payload["example"]
    result = M01LessonResult.model_validate(dict(
        title="Name it and say its colour",
        explanation=(
            "Say what each object is, then describe it: the object, then its colour, "
            "which matches the noun." + (f" For example: {example}" if example else "")
        ),
        questions=questions,
    ))
    validate_m01_lesson(payload, result)
    return result


M01_GENERATION = MissionGeneration(
    M01_PROMPT_VERSION,
    M01_SCHEMA_VERSION,
    M01_VALIDATOR_VERSION,
    "",
    M01LessonResult,
    validate_m01_lesson,
    fallback_m01_lesson,
    "mission_lesson_m01_v2",
    uses_model=False,
)
