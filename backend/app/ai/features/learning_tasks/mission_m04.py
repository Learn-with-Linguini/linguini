"""Deterministic, validated three-question lesson for A1 mission M04."""

from __future__ import annotations

import random
from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.mission import (
    fold,
    tokens,
    unique_question_ids,
)
from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.roleplay import parse_roleplay_facts

type M04Purpose = Literal["chooseOwner", "buildMine", "buildTheirs"]

_INTERACTIONS = {
    "chooseOwner": "multipleChoice",
    "buildMine": "sentenceBuilding",
    "buildTheirs": "sentenceBuilding",
}
_ORDER = ["chooseOwner", "buildMine", "buildTheirs"]
SECTION_MATCH = "Task 1 · Whose is it?"
SECTION_BUILD = "Task 2 · Say whose it is"


class M04Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M04Purpose
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=40)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=64)
    section: NonEmptyText = Field(max_length=80)
    roleplay_premise: NonEmptyText = Field(max_length=240)
    prompt_translation: Annotated[str, Field(max_length=300)] | None
    markers: dict[str, int]

    @model_validator(mode="after")
    def validate_interaction(self) -> M04Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        return self


class M04LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[M04Question], Field(min_length=3, max_length=3)]


def _fail(message):
    raise LearningTaskGenerationError(message)


def _facts(payload):
    markers = payload.get("all_markers") or {}
    facts = parse_roleplay_facts(payload.get("facts"), markers)
    if facts is None or any(fact.fact_type != "ownership" for fact in facts):
        _fail("M04 needs valid, explicitly assigned ownership facts.")
    roles = {(fact.owner_type, tuple(fact.owner_names)) for fact in facts}
    expected_roles = {
        ("learner", ()),
        ("namedCharacter", ("Ana",)),
        ("namedCharacter", ("Leo",)),
    }
    if len(facts) != 3:
        _fail("M04 requires exactly three assigned ownership facts.")
    if roles != expected_roles or len(roles) != len(facts):
        _fail("M04 facts must match its learner, Ana, and Leo assignment.")
    object_ids = {str(fact.scene_object_id) for fact in facts}
    if (
        not facts
        or object_ids != set(markers)
        or any(number < 1 for number in markers.values())
        or len(set(markers.values())) != len(markers)
    ):
        _fail("M04 marker assignments must cover each fact object exactly once.")
    return facts


def _build_bank(answer, contrast, rng):
    answer_tokens = tokens(answer)
    extras = list((Counter(tokens(contrast)) - Counter(answer_tokens)).elements())[:2]
    bank = [*answer_tokens, *extras]
    rng.shuffle(bank)
    return bank


def _validate_bank(question, answer, contrast):
    answer_tokens = tokens(answer)
    extras = list((Counter(tokens(contrast)) - Counter(answer_tokens)).elements())[:2]
    if question.translation is not None:
        _fail("Sentence-building answers must not be given by a translation.")
    if Counter(question.token_bank) != Counter([*answer_tokens, *extras]):
        _fail("The word bank may add at most two tokens from the contrast sentence.")


def validate_m04_lesson(payload: dict[str, Any], result: M04LessonResult) -> None:
    """Require the three taught ownership questions and facts from this pretend plan."""
    facts = _facts(payload)
    fact_ids = {str(fact.scene_object_id) for fact in facts}
    details = {item["objectKey"]: item for item in payload["fact_details"]}
    learner, ana = payload["learner"], payload["ana"]
    if result.title != "Say what is yours":
        _fail("The lesson title must match M04.")
    questions = result.questions
    unique_question_ids(questions)
    if [question.purpose for question in questions] != _ORDER:
        _fail("M04 questions go: choose, then build mine and theirs.")
    choose, mine, theirs = questions

    choice = payload["choice"]
    leo = payload["leo"]
    if (
        choice.get("objectKey") != leo.get("objectKey")
        or choice.get("sentence") != leo.get("sentence")
        or choice.get("contrast") != leo.get("contrast")
        or choice.get("other_object_sentence") != leo.get("other_object_sentence")
    ):
        _fail("The ownership choice must use Leo's assigned fact.")
    expected_choice_markers = {choice["objectKey"]: choice["marker"]}
    if (
        choose.section != SECTION_MATCH
        or choose.prompt != payload["choose_prompt"]
        or choose.roleplay_premise != choice["premise"]
        or choose.markers != expected_choice_markers
        or choose.object_key != choice["objectKey"]
        or choose.prompt_translation != payload["choose_prompt_translation"]
        or choose.translation is not None
    ):
        _fail("The choice question must use the assigned subject and its premise.")
    if choose.interaction_type != "multipleChoice":
        _fail("The ownership choice question must be multiple choice.")
    if fold(choose.prompt) != fold(payload["choose_prompt"]):
        _fail("The ownership choice prompt must match the reviewed language.")
    if (
        len(choose.options) != 3
        or len({option.option_id for option in choose.options}) != 3
        or len({fold(option.label) for option in choose.options}) != 3
    ):
        _fail("The ownership choice must have three distinct sentences.")
    if {fold(option.label) for option in choose.options} != {
        fold(choice[key]) for key in ("sentence", "contrast", "other_object_sentence")
    }:
        _fail("Ownership choices must use only the taught perspectives and fact objects.")
    if choose.correct_option_id not in {option.option_id for option in choose.options}:
        _fail("The ownership choice must identify one offered answer.")
    if fold(next(
        option.label for option in choose.options
        if option.option_id == choose.correct_option_id
    )) != fold(choice["sentence"]):
        _fail("The correct ownership choice must match its assigned fact.")
    if choose.markers != expected_choice_markers:
        _fail("The choice question highlights only its assigned object.")

    for question, expected, purpose, section in (
        (mine, learner, "buildMine", SECTION_BUILD),
        (theirs, ana, "buildTheirs", SECTION_BUILD),
    ):
        if (
            question.purpose != purpose
            or question.section != section
            or question.object_key != expected["objectKey"]
            or question.prompt != expected["build_prompt"]
            or question.roleplay_premise != expected["premise"]
            or question.markers != {expected["objectKey"]: expected["marker"]}
            or question.prompt_translation != expected["build_prompt_translation"]
            or question.interaction_type != "sentenceBuilding"
            or question.options
            or question.correct_option_id is not None
            or question.correct_text != expected["sentence"]
        ):
            _fail("Sentence builders must use the assigned singular owner and taught prompt.")
        _validate_bank(question, expected["sentence"], expected["contrast"])
    if set(details) != fact_ids:
        _fail("Every fact object must have a reviewed rendering.")


def assemble_m04_lesson(payload: dict[str, Any]) -> M04LessonResult:
    """Build the deterministic M04 lesson from the saved roleplay plan."""
    _facts(payload)
    rng = random.Random(payload.get("seed") or "M04")
    ana = payload["ana"]
    choice = payload["choice"]
    choose_options = [
        dict(option_id="owner-correct", label=choice["sentence"]),
        dict(option_id="owner-other-perspective", label=choice["contrast"]),
        dict(option_id="owner-other-object", label=choice["other_object_sentence"]),
    ]
    rng.shuffle(choose_options)
    choose = dict(
        question_id="choose-owner",
        purpose="chooseOwner",
        prompt=payload["choose_prompt"],
        interaction_type="multipleChoice",
        options=choose_options,
        correct_option_id="owner-correct",
        correct_text=None,
        token_bank=[],
        translation=None,
        object_key=choice["objectKey"],
        section=SECTION_MATCH,
        roleplay_premise=choice["premise"],
        prompt_translation=payload["choose_prompt_translation"],
        markers={choice["objectKey"]: choice["marker"]},
    )
    build_questions = []
    for question_id, purpose, fact in (
        ("build-mine", "buildMine", payload["learner"]),
        ("build-theirs", "buildTheirs", ana),
    ):
        build_questions.append(dict(
            question_id=question_id,
            purpose=purpose,
            prompt=fact["build_prompt"],
            interaction_type="sentenceBuilding",
            options=[],
            correct_option_id=None,
            correct_text=fact["sentence"],
            token_bank=_build_bank(fact["sentence"], fact["contrast"], rng),
            translation=None,
            object_key=fact["objectKey"],
            section=SECTION_BUILD,
            roleplay_premise=fact["premise"],
            prompt_translation=fact["build_prompt_translation"],
            markers={fact["objectKey"]: fact["marker"]},
        ))
    result = M04LessonResult.model_validate(dict(
        title="Say what is yours", questions=[choose, *build_questions],
    ))
    validate_m04_lesson(payload, result)
    return result


