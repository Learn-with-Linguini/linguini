"""M03 A1 mission lesson: say how many of an object there are.

The lesson is built deterministically from the learner-counted group, the taught
number range and reviewed plurals, and accepted only through
``validate_m03_lesson``.
"""

from __future__ import annotations

import random
import re
from collections import Counter
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
from app.services.quantities import NUMBER_WORDS, quantity_sentence

M03_PROMPT_VERSION = "learning-tasks.m03-a1.v2"
M03_SCHEMA_VERSION = "learning-tasks-m03-result.v2"
M03_VALIDATOR_VERSION = "learning-tasks-m03-validator.v2"

type M03Purpose = Literal["chooseQuantity", "buildQuantity", "matchQuantity"]

_INTERACTIONS = {
    "chooseQuantity": "multipleChoice",
    "buildQuantity": "sentenceBuilding",
    "matchQuantity": "multipleChoice",
}
_ORDER = ["chooseQuantity", "buildQuantity", "matchQuantity"]
SECTION_PHOTO = "Task 1 · Count in your photo"
SECTION_BOARD = "Task 2 · Practice board"
_ANSWER_PROMPTS = {
    "es": "Responde con una frase.", "fr": "Réponds avec une phrase.",
    "de": "Antworte mit einem Satz.",
}
_BOARD_LETTERS = "abc"
_DIGIT = re.compile(r"\d")


class M03Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M03Purpose
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=20)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=200)
    section: Annotated[str, Field(max_length=80)] | None = None
    group_object_ids: list[NonEmptyText] = []
    board_counts: dict[str, int] | None = None
    board_object_id: Annotated[str, Field(max_length=64)] | None = None
    quantity_word: Annotated[str, Field(max_length=40)] | None = None

    @model_validator(mode="after")
    def validate_interaction(self) -> M03Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        return self


class M03LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[M03Question], Field(min_length=3, max_length=3)]


def _taught(payload):
    bounds = payload["numberRange"]
    words = NUMBER_WORDS[payload["targetLanguage"]]
    return [number for number in range(bounds["low"], bounds["high"] + 1) if number in words]


def _nearby(number, taught, *, skip_first=False):
    """Taught quantities nearest to ``number``: ±2, ±1, then ±3, ±4, … outward."""
    steps = [2, -2, 1, -1] + [step for gap in range(3, 21) for step in (gap, -gap)]
    if skip_first:
        steps = [1, -1, 2, -2] + [step for gap in range(3, 21) for step in (gap, -gap)]
    found, seen = [], {number}
    for step in steps:
        other = number + step
        if other in taught and other not in seen:
            seen.add(other)
            found.append(other)
    return found


def _boards(question):
    counts = question.board_counts or {}
    if set(counts) != {option.option_id for option in question.options}:
        raise LearningTaskGenerationError("Board counts must cover exactly the options.")
    if len(set(counts.values())) != len(counts):
        raise LearningTaskGenerationError("Board counts must be distinct.")
    return counts


def validate_m03_lesson(payload: dict[str, Any], result: M03LessonResult) -> None:
    """Check the counted-group reference, taught numbers, plural and board consistency."""
    group = payload["group"]
    if group is None:
        raise LearningTaskGenerationError("The lesson needs a counted group with a regular plural.")
    questions = result.questions
    unique_question_ids(questions)
    if [question.purpose for question in questions] != _ORDER:
        raise LearningTaskGenerationError("Questions go: choose, build, then the practice board.")
    choose, build, match = questions
    language = payload["targetLanguage"]
    words = NUMBER_WORDS[language]
    taught = set(_taught(payload))
    taught_words = {fold(words[number]) for number in taught}
    for question in questions:
        if question.object_key != group["objectKey"]:
            raise LearningTaskGenerationError("Questions must refer to the counted group.")
    if choose.section != SECTION_PHOTO or build.section != SECTION_PHOTO:
        raise LearningTaskGenerationError("Photo questions belong to the counting section.")
    if match.section != SECTION_BOARD:
        raise LearningTaskGenerationError("The practice board uses its own section.")
    for question in (choose, build):
        if set(question.group_object_ids) != set(group["objectIds"]):
            raise LearningTaskGenerationError("Photo questions must highlight the counted group.")
    if len(choose.options) > 3:
        raise LearningTaskGenerationError("Number choices stay under four options.")
    if checked_answer(choose) != fold(group["numberWord"]):
        raise LearningTaskGenerationError("The correct choice must be the confirmed count's word.")
    labels = {fold(option.label) for option in choose.options}
    if not labels <= taught_words:
        raise LearningTaskGenerationError("Choices must be taught number words.")
    if any(_DIGIT.search(option.label) for option in choose.options):
        raise LearningTaskGenerationError("Number choices are words, never digits.")
    if build.options or build.correct_option_id is not None:
        raise LearningTaskGenerationError("Sentence building cannot offer options.")
    if build.translation is not None:
        raise LearningTaskGenerationError("The build prompt must not give away the count.")
    if fold(build.correct_text or "") != fold(group["statement"]):
        raise LearningTaskGenerationError("The built sentence must be the confirmed statement.")
    extras = Counter(map(fold, build.token_bank)) - Counter(map(fold, tokens(group["statement"])))
    if sum(extras.values()) != 2 or fold(group["singular"]) not in extras:
        raise LearningTaskGenerationError("The bank adds the singular and one wrong number.")
    extra_word = next(word for word in extras if word != fold(group["singular"]))
    if extra_word not in taught_words or extra_word == fold(group["numberWord"]):
        raise LearningTaskGenerationError("The extra bank number must be another taught word.")
    counts = _boards(match)
    checked_answer(match)
    if not all(count in taught for count in counts.values()):
        raise LearningTaskGenerationError("Board counts must stay within the taught range.")
    target = counts[match.correct_option_id]
    if any(count == target for option_id, count in counts.items()
           if option_id != match.correct_option_id):
        raise LearningTaskGenerationError("Only one board may match the sentence.")
    if match.quantity_word != words.get(target):
        raise LearningTaskGenerationError("The board question names its target number word.")
    expected = quantity_sentence(language, match.quantity_word, group["plural"])
    if fold(match.prompt) != fold(expected):
        raise LearningTaskGenerationError("The board prompt must be the target statement.")
    if match.translation is not None:
        raise LearningTaskGenerationError("The practice board keeps its sentence untranslated.")


def _choose_question(group, words, taught, rng):
    distractors = _nearby(group["quantity"], taught, skip_first=True)
    labels = [words[group["quantity"]], *(words[number] for number in distractors[:2])]
    rng.shuffle(labels)
    options = [
        dict(option_id=f"number-{_BOARD_LETTERS[index]}", label=label)
        for index, label in enumerate(labels)
    ]
    correct = options[labels.index(words[group["quantity"]])]["option_id"]
    return dict(
        question_id="choose-quantity", purpose="chooseQuantity",
        prompt=group["question"], interaction_type="multipleChoice",
        options=options, correct_option_id=correct, correct_text=None,
        token_bank=[], translation=None, object_key=group["objectKey"],
        section=SECTION_PHOTO, group_object_ids=group["objectIds"],
        board_counts=None, board_object_id=None, quantity_word=None,
    ), distractors


def _build_question(payload, group, distractor, rng):
    language = payload["targetLanguage"]
    bank = [*tokens(group["statement"]), group["singular"], NUMBER_WORDS[language][distractor]]
    rng.shuffle(bank)
    return dict(
        question_id="build-quantity", purpose="buildQuantity",
        prompt=f"{group['question']} {_ANSWER_PROMPTS[language]}",
        interaction_type="sentenceBuilding", options=[], correct_option_id=None,
        correct_text=group["statement"], token_bank=bank, translation=None,
        object_key=group["objectKey"], section=SECTION_PHOTO,
        group_object_ids=group["objectIds"], board_counts=None,
        board_object_id=None, quantity_word=None,
    )


def _match_question(payload, group, taught, rng):
    language = payload["targetLanguage"]
    words = NUMBER_WORDS[language]
    quantity = group["quantity"]
    greater = [number for number in taught if number > quantity]
    others = [number for number in taught if number != quantity]
    target = rng.choice(greater or others) if greater or others else quantity
    counts = [target, *_nearby(target, taught)[:2]]
    rng.shuffle(counts)
    options = [
        dict(
            option_id=f"board-{_BOARD_LETTERS[index]}",
            label=f"Board {_BOARD_LETTERS[index].upper()}",
        )
        for index in range(len(counts))
    ]
    return dict(
        question_id="match-quantity", purpose="matchQuantity",
        prompt=quantity_sentence(language, words[target], group["plural"]),
        interaction_type="multipleChoice", options=options,
        correct_option_id=options[counts.index(target)]["option_id"],
        correct_text=None, token_bank=[], translation=None,
        object_key=group["objectKey"], section=SECTION_BOARD, group_object_ids=[],
        board_counts={options[index]["option_id"]: count for index, count in enumerate(counts)},
        board_object_id=group["boardObjectId"], quantity_word=words[target],
    )


def fallback_m03_lesson(payload: dict[str, Any]) -> M03LessonResult:
    """The deterministic three-question lesson, seeded by the session."""
    group = payload["group"]
    if group is None:
        raise LearningTaskGenerationError("The lesson needs a counted group with a regular plural.")
    language = payload["targetLanguage"]
    taught = _taught(payload)
    if len(taught) < 2:
        raise LearningTaskGenerationError("The lesson needs at least two taught numbers.")
    rng = random.Random(payload.get("seed") or "M03")
    choose, distractors = _choose_question(group, NUMBER_WORDS[language], taught, rng)
    build = _build_question(payload, group, distractors[0], rng)
    match = _match_question(payload, group, taught, rng)
    result = M03LessonResult.model_validate(dict(
        title="Say how many", questions=[choose, build, match],
    ))
    validate_m03_lesson(payload, result)
    return result


M03_GENERATION = MissionGeneration(
    M03_PROMPT_VERSION,
    M03_SCHEMA_VERSION,
    M03_VALIDATOR_VERSION,
    "",
    M03LessonResult,
    validate_m03_lesson,
    fallback_m03_lesson,
    "mission_lesson_m03_v2",
    uses_model=False,
)
