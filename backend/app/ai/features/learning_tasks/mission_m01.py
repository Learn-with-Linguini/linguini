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

M01_PROMPT_VERSION = "learning-tasks.m01-a1.v4"
M01_SCHEMA_VERSION = "learning-tasks-m01-result.v4"
M01_VALIDATOR_VERSION = "learning-tasks-m01-validator.v4"

type M01Purpose = Literal["confirmObject", "chooseAttribute", "describeObject"]

IDENTIFY_SECTION = "Task 1 · Identify objects in your photo"
DESCRIBE_SECTION = "Task 2 · Describe them"
CONFIRM_IDS = ("confirm-first", "confirm-second")
_ORDER: list[M01Purpose] = [
    "confirmObject", "confirmObject", "chooseAttribute", "describeObject",
]
_INTERACTIONS = {
    "confirmObject": "multipleChoice",
    "chooseAttribute": "multipleChoice",
    "describeObject": "sentenceBuilding",
}
_SECTIONS = {
    "confirmObject": IDENTIFY_SECTION,
    "chooseAttribute": DESCRIBE_SECTION,
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
    """The taught sentence for one pair: ``Es una manzana roja.``, ``C'est une petite tasse.``"""
    article, noun = pair["nounPhrase"].split(" ", 1)
    words = [article, pair["agreedForm"], noun] if pair["before"] else [
        article, noun, pair["agreedForm"],
    ]
    return f"{payload['sentenceStart']} {' '.join(words)}."


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
        raise LearningTaskGenerationError("Confirm both objects, choose a detail, then describe.")
    if [question.object_key for question in questions] != [
        first["key"], second["key"], first["key"], second["key"]
    ]:
        raise LearningTaskGenerationError("Each task asks about both selected objects.")
    for question in questions:
        if question.section != _SECTIONS[question.purpose]:
            raise LearningTaskGenerationError("Questions belong to their task.")
        if question.interaction_type == "multipleChoice" and question.translation:
            raise LearningTaskGenerationError("Choices never reveal a translation.")
    first_check, second_check, attribute, describe = questions
    for confirm, shown, other in ((first_check, first, second), (second_check, second, first)):
        correct = checked_answer(confirm)
        named = other if confirm.statement_correct is False else shown
        right, contrast = confirm_answers(payload, shown, other)[confirm.statement_correct]
        if fold(confirm.prompt) != fold(statement(payload, named["nounPhrase"])):
            raise LearningTaskGenerationError(
                "A statement names the shown object or the other confirmed object."
            )
        if confirm.attribute_keys or correct != fold(right) or set(_labels(confirm)) != {
            fold(right), fold(contrast)
        }:
            raise LearningTaskGenerationError("Yes/no answers are the two taught chunks.")

    correct = checked_answer(attribute)
    allowed = {fold(form) for form in payload["attributeOptions"]}
    if attribute.attribute_keys != [first["attributeKey"]] or correct != fold(first["agreedForm"]):
        raise LearningTaskGenerationError("The answer is the confirmed detail's agreed form.")
    if not set(_labels(attribute)) <= allowed:
        raise LearningTaskGenerationError("Options are taught, clearly different details.")

    sentence = description(payload, second)
    built = fold(describe.correct_text or "")
    if describe.attribute_keys != [second["attributeKey"]] or built != fold(sentence):
        raise LearningTaskGenerationError(
            "Descriptions use the taught pattern with the object's confirmed detail."
        )
    extras = [fold(word) for word in payload["describeExtras"]]
    checked_answer(describe.model_copy(update={"token_bank": [
        word for word in describe.token_bank if fold(word) not in extras
    ]}))
    if len(describe.token_bank) != len(tokens(sentence)) + len(extras):
        raise LearningTaskGenerationError("Extra tiles are only the reviewed agreement forms.")


def _a(word: str) -> str:
    return f"{'an' if word[:1].casefold() in 'aeiou' else 'a'} {word}"


def _options(prefix: str, labels: list[str], order: list[int]) -> list[dict[str, str]]:
    return [
        dict(option_id=f"{prefix}-{index}", label=capitalised(labels[position]))
        for index, position in enumerate(order, 1)
    ]


def fallback_m01_lesson(payload: dict[str, Any]) -> M01LessonResult:
    """The deterministic M01 lesson; it passes the same validator.

    Option order and each yes/no statement's truth come from ``payload['layout']``,
    which the payload derives from the session, so a rebuilt lesson matches the saved one.
    """
    pairs = payload["pairs"]
    if len(pairs) != 2:
        raise LearningTaskGenerationError("The lesson needs two confirmed object-colour pairs.")
    first, second = pairs
    layout = payload["layout"]
    details = _options("attribute", payload["attributeOptions"], layout["attributeOrder"])
    sentence = description(payload, second)

    def picked(options, label):
        return next(item["option_id"] for item in options if fold(item["label"]) == fold(label))

    base = dict(correct_text=None, token_bank=[], translation=None, attribute_keys=[])
    checks = []
    for index, (shown, other) in enumerate(((first, second), (second, first))):
        truth = layout["statementCorrect"][index]
        named = shown if truth else other
        right, contrast = confirm_answers(payload, shown, other)[truth]
        options = _options("confirm", [right, contrast], layout["confirmOrders"][index])
        checks.append(dict(
            base, question_id=CONFIRM_IDS[index], purpose="confirmObject",
            section=IDENTIFY_SECTION, prompt=statement(payload, named["nounPhrase"]),
            interaction_type="multipleChoice", options=options,
            correct_option_id=picked(options, right), object_key=shown["key"],
            statement_correct=truth,
        ))
    questions = [
        *checks,
        dict(base, question_id="choose-attribute", purpose="chooseAttribute",
             section=DESCRIBE_SECTION, prompt=payload["attributePrompt"],
             interaction_type="multipleChoice", options=details,
             correct_option_id=picked(details, first["agreedForm"]), object_key=first["key"],
             attribute_keys=[first["attributeKey"]]),
        dict(question_id="describe-object", purpose="describeObject",
             section=DESCRIBE_SECTION, prompt=payload["describePrompt"],
             interaction_type="sentenceBuilding", options=[], correct_option_id=None,
             correct_text=sentence,
             token_bank=sorted([*tokens(sentence), *payload["describeExtras"]], key=fold),
             translation=f"It's {_a(second['attributeSource'])} {second['source']}.",
             object_key=second["key"], attribute_keys=[second["attributeKey"]]),
    ]
    example = payload["example"]
    result = M01LessonResult.model_validate(dict(
        title="Name it and describe it",
        explanation=(
            "Say what each object is, then describe it with a detail from your photo, such "
            "as its colour, size or material, matching the noun."
            + (f" For example: {example}" if example else "")
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
