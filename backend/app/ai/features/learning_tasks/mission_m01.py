"""M01 A1 mission lesson: identify two photo objects, then describe their colours.

Task 1 identifies objects: Q1 names the first object by choice and Q2 confirms or
rejects a statement about the second. Task 2 describes them: Q3 chooses the first
object's colour and Q4 builds the second object's description. The payload holds the
two learner-confirmed object-colour pairs with reviewed target-language forms and the
taught nouns and colours that may appear as options. The lesson is built
deterministically and accepted only through ``validate_m01_lesson``.
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

M01_PROMPT_VERSION = "learning-tasks.m01-a1.v3"
M01_SCHEMA_VERSION = "learning-tasks-m01-result.v3"
M01_VALIDATOR_VERSION = "learning-tasks-m01-validator.v3"

type M01Purpose = Literal["identifyObject", "confirmObject", "chooseColour", "describeObject"]

IDENTIFY_SECTION = "Task 1 · Identify objects in your photo"
DESCRIBE_SECTION = "Task 2 · Describe their colours"
_ORDER: list[M01Purpose] = ["identifyObject", "confirmObject", "chooseColour", "describeObject"]
_INTERACTIONS = {
    "identifyObject": "multipleChoice",
    "confirmObject": "multipleChoice",
    "chooseColour": "multipleChoice",
    "describeObject": "sentenceBuilding",
}
_SECTIONS = {
    "identifyObject": IDENTIFY_SECTION,
    "confirmObject": IDENTIFY_SECTION,
    "chooseColour": DESCRIBE_SECTION,
    "describeObject": DESCRIBE_SECTION,
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
    """The taught sentence for one pair, e.g. ``Es una manzana roja.``"""
    return f"{payload['sentenceStart']} {pair['nounPhrase']} {pair['agreedForm']}."


def statement(payload: dict[str, Any], noun_phrase: str) -> str:
    """The yes/no question naming ``noun_phrase``, e.g. ``¿Es un libro?``"""
    return payload["confirmPrompt"].format(noun=noun_phrase)


def confirm_answers(payload: dict[str, Any], shown: dict[str, Any], other: dict[str, Any]):
    """Correct and contrasting chunks for a statement that is true or false.

    The correct answer always names the shown object; the contrasting answer names
    the other taught confirmed object with the opposite yes/no.
    """
    yes, no = payload["yes"], payload["no"]
    start = payload["sentenceStart"]
    return {
        True: (f"{yes}, {start.lower()} {shown['nounPhrase']}.",
               f"{no}, {start.lower()} {other['nounPhrase']}."),
        False: (f"{no}, {start.lower()} {shown['nounPhrase']}.",
                f"{yes}, {start.lower()} {other['nounPhrase']}."),
    }


def _labels(question) -> list[str]:
    return [fold(option.label) for option in question.options]


def validate_m01_lesson(payload: dict[str, Any], result: M01LessonResult) -> None:
    """Two tasks on the two selected pairs; every option is a taught confirmed fact."""
    pairs = payload["pairs"]
    questions = result.questions
    unique_question_ids(questions)
    if len(pairs) != 2 or fold(pairs[0]["source"]) == fold(pairs[1]["source"]):
        raise LearningTaskGenerationError("The lesson needs two different confirmed objects.")
    first, second = pairs
    if [question.purpose for question in questions] != _ORDER:
        raise LearningTaskGenerationError("Identify, confirm, choose a colour, then describe.")
    if [question.object_key for question in questions] != [
        first["key"], second["key"], first["key"], second["key"]
    ]:
        raise LearningTaskGenerationError("Each task asks about both selected objects.")
    for question in questions:
        if question.section != _SECTIONS[question.purpose]:
            raise LearningTaskGenerationError("Questions belong to their task.")
        if question.interaction_type == "multipleChoice" and question.translation:
            raise LearningTaskGenerationError("Choices never reveal a translation.")
    identify, confirm, colour, describe = questions

    correct = checked_answer(identify)
    taught = {fold(noun) for noun in payload["taughtNouns"]}
    if identify.attribute_keys or correct != fold(first["nounPhrase"]):
        raise LearningTaskGenerationError("Identification answers name the shown object.")
    if not set(_labels(identify)) <= taught or fold(second["nounPhrase"]) not in _labels(identify):
        raise LearningTaskGenerationError("Identification options are taught object names.")

    correct = checked_answer(confirm)
    named = first if confirm.statement_correct is False else second
    right, contrast = confirm_answers(payload, second, first)[confirm.statement_correct]
    if fold(confirm.prompt) != fold(statement(payload, named["nounPhrase"])):
        raise LearningTaskGenerationError("A false statement names the other confirmed object.")
    if confirm.attribute_keys or correct != fold(right) or set(_labels(confirm)) != {
        fold(right), fold(contrast)
    }:
        raise LearningTaskGenerationError("Yes/no answers are the two taught chunks.")

    correct = checked_answer(colour)
    allowed = {fold(form) for form in payload["colourOptions"]}
    if colour.attribute_keys != [first["colourKey"]] or correct != fold(first["agreedForm"]):
        raise LearningTaskGenerationError("The colour answer is the confirmed, agreed colour.")
    if not set(_labels(colour)) <= allowed:
        raise LearningTaskGenerationError("Colour options are taught, clearly different colours.")

    sentence = description(payload, second)
    built = fold(describe.correct_text or "")
    if describe.attribute_keys != [second["colourKey"]] or built != fold(sentence):
        raise LearningTaskGenerationError(
            "Descriptions use the taught pattern with the object's confirmed colour."
        )
    extras = [fold(word) for word in payload["describeExtras"]]
    checked_answer(describe.model_copy(update={"token_bank": [
        word for word in describe.token_bank if fold(word) not in extras
    ]}))
    if len(describe.token_bank) != len(tokens(sentence)) + len(extras):
        raise LearningTaskGenerationError("Extra tiles are only the reviewed agreement forms.")


def _options(prefix: str, labels: list[str], order: list[int]) -> list[dict[str, str]]:
    return [
        dict(option_id=f"{prefix}-{index}", label=capitalised(labels[position]))
        for index, position in enumerate(order, 1)
    ]


def fallback_m01_lesson(payload: dict[str, Any]) -> M01LessonResult:
    """The deterministic M01 lesson; it passes the same validator.

    Option order and the yes/no statement come from ``payload['layout']``, which the
    payload derives from the session, so a rebuilt lesson matches the saved one.
    """
    pairs = payload["pairs"]
    if len(pairs) != 2:
        raise LearningTaskGenerationError("The lesson needs two confirmed object-colour pairs.")
    first, second = pairs
    layout = payload["layout"]
    nouns = payload["identifyOptions"]
    identify = _options("identify", nouns, layout["identifyOrder"])
    truth = layout["statementCorrect"]
    named = second if truth else first
    right, contrast = confirm_answers(payload, second, first)[truth]
    confirm_labels = [right, contrast]
    confirm = _options("confirm", confirm_labels, layout["confirmOrder"])
    colours = payload["colourOptions"]
    colour = _options("colour", colours, layout["colourOrder"])
    sentence = description(payload, second)

    def picked(options, label):
        return next(item["option_id"] for item in options if fold(item["label"]) == fold(label))

    base = dict(correct_text=None, token_bank=[], translation=None, attribute_keys=[])
    questions = [
        dict(base, question_id="identify-object", purpose="identifyObject",
             section=IDENTIFY_SECTION, prompt=payload["identifyPrompt"],
             interaction_type="multipleChoice", options=identify,
             correct_option_id=picked(identify, first["nounPhrase"]), object_key=first["key"]),
        dict(base, question_id="confirm-object", purpose="confirmObject",
             section=IDENTIFY_SECTION, prompt=statement(payload, named["nounPhrase"]),
             interaction_type="multipleChoice", options=confirm,
             correct_option_id=picked(confirm, right), object_key=second["key"],
             statement_correct=truth),
        dict(base, question_id="choose-colour", purpose="chooseColour",
             section=DESCRIBE_SECTION, prompt=payload["colourPrompt"],
             interaction_type="multipleChoice", options=colour,
             correct_option_id=picked(colour, first["agreedForm"]), object_key=first["key"],
             attribute_keys=[first["colourKey"]]),
        dict(question_id="describe-object", purpose="describeObject",
             section=DESCRIBE_SECTION, prompt=payload["describePrompt"],
             interaction_type="sentenceBuilding", options=[], correct_option_id=None,
             correct_text=sentence,
             token_bank=sorted([*tokens(sentence), *payload["describeExtras"]], key=fold),
             translation=f"It's a {second['colourSource']} {second['source']}.",
             object_key=second["key"], attribute_keys=[second["colourKey"]]),
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
    "mission_lesson_m01_v3",
    uses_model=False,
)
