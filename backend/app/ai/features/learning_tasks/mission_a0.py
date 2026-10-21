"""A0 scene mission lessons: M01, M02, M03 and M13 at the A0 (pre-A1) level.

Each lesson is two tasks of three questions on two focus objects (M03: the
learner-counted group, then a practice board). Lessons are built
deterministically from the payload's closed, reviewed content and accepted only
through ``validate_a0_lesson``; no model call is made.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import Field

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
from app.services.a0_lexicon import KOREAN_ENDINGS

type A0Purpose = Literal[
    "matchName", "confirmName", "buildIdentify",
    "findNamed", "chooseName", "listenSelect",
    "countGroup", "matchChunk", "buildChunk",
    "chooseChunk", "matchSpoken", "fillSlot",
]

ORDERS: dict[str, list[str]] = {
    "M01": ["matchName", "confirmName", "buildIdentify"],
    "M02": ["findNamed", "chooseName", "listenSelect"],
    "M03": ["countGroup", "matchChunk", "buildChunk"],
    "M13": ["chooseChunk", "matchSpoken", "fillSlot"],
}
MARKER_PURPOSES = {"matchName", "findNamed", "listenSelect", "matchSpoken"}
BUILD_PURPOSES = {"buildIdentify", "buildChunk"}
# English prompts and instructions an A0 question may show; target-language text
# always comes from the payload's approved chunks.
INSTRUCTIONS = {
    "matchName": "Listen, then tap the marker for this word.",
    "confirmName": "Look at the highlighted object. Answer yes or no.",
    "buildIdentify": "Build the answer with the tiles.",
    "findNamed": "Tap the marker for the object.",
    "chooseName": "Which word names the highlighted object?",
    "listenSelect": "Listen, then tap the marker for the object you hear.",
    "countGroup": "Count the highlighted group. How many are there?",
    "matchChunk": "Which words match what you see?",
    "buildChunk": "Build the words with the tiles.",
    "chooseChunk": "Which words go with the highlighted object?",
    "matchSpoken": "Listen, then tap the marker for the object you hear.",
    "fillSlot": "Choose the word that completes the noun.",
}
SLOT = "___"
_DIGIT = re.compile(r"\d")
MAX_OPTIONS = 3

A0_SCHEMA_VERSION = "learning-tasks-a0-result.v1"
A0_VALIDATOR_VERSION = "learning-tasks-a0-validator.v1"


class A0Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: A0Purpose
    section: NonEmptyText = Field(max_length=80)
    prompt: NonEmptyText = Field(max_length=300)
    instruction: NonEmptyText = Field(max_length=200)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=MAX_OPTIONS)] = []
    correct_option_id: Annotated[str, Field(max_length=64)] | None = None
    correct_text: Annotated[str, Field(max_length=300)] | None = None
    token_bank: list[Annotated[NonEmptyText, Field(max_length=40)]] = []
    translation: Annotated[str, Field(max_length=300)] | None = None
    prompt_translation: Annotated[str, Field(max_length=300)] | None = None
    object_key: NonEmptyText = Field(max_length=200)
    # Marker questions: option id -> the approved object behind that marker.
    marker_keys: dict[str, str] | None = None
    # Marker questions: other markers on an object with the same name, equally right.
    accepted_option_ids: list[str] = []
    # Yes/no questions: whether the statement is true of the highlighted object.
    statement_true: bool | None = None
    # The stated object of a yes/no question.
    stated_key: str | None = None
    audio_text: Annotated[str, Field(max_length=300)] | None = None
    listen_first: bool = False
    group_object_ids: list[NonEmptyText] = []
    display_count: int | None = None
    board_object_id: str | None = None
    slot_template: Annotated[str, Field(max_length=120)] | None = None
    # The complete chunk shown and played once the slot is graded.
    complete_chunk: Annotated[str, Field(max_length=120)] | None = None


class A0LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[A0Question], Field(min_length=6, max_length=6)]


def _rng(payload, salt):
    return random.Random(f"{payload['seed']}:{salt}")


def _objects(payload):
    return {row["key"]: row for row in payload["approvedObjects"]}


def _marker_question(payload, purpose, section, target, prompt, *, listen_first=False,
                     index):
    objects = sorted(payload["approvedObjects"], key=lambda row: row["marker"])
    noun = fold(target["noun"])
    shown = objects[:MAX_OPTIONS]
    if target["key"] not in {row["key"] for row in shown}:
        shown = [*shown[:MAX_OPTIONS - 1], target]
    if all(fold(row["noun"]) == noun for row in shown):
        # Keep a differently named object so the question stays a choice.
        other = next((row for row in objects if fold(row["noun"]) != noun), None)
        if other is not None:
            rest = [row for row in shown if row["key"] != target["key"]]
            shown = [target, *rest][:MAX_OPTIONS - 1] + [other]
    shown.sort(key=lambda row: row["marker"])
    options = [dict(option_id=f"marker-{row['marker']}", label=str(row["marker"]))
               for row in shown]
    return dict(
        question_id=f"{purpose}-{index}", purpose=purpose, section=section,
        prompt=prompt, instruction=INSTRUCTIONS[purpose],
        interaction_type="multipleChoice", options=options,
        correct_option_id=f"marker-{target['marker']}",
        marker_keys={f"marker-{row['marker']}": row["key"] for row in shown},
        # The prompt only names the object, so any object with that name is right.
        accepted_option_ids=[
            f"marker-{row['marker']}" for row in shown
            if row["key"] != target["key"] and fold(row["noun"]) == noun
        ],
        object_key=target["key"], audio_text=prompt, listen_first=listen_first,
        prompt_translation=payload["approvedTranslations"].get(prompt),
    )


def _choice_question(payload, purpose, section, target, prompt, labels, correct, *,
                     index, shuffle=True, **extra):
    labels = list(dict.fromkeys(labels))
    if shuffle:
        _rng(payload, f"{purpose}-{index}").shuffle(labels)
    options = [dict(option_id=f"option-{number}", label=label)
               for number, label in enumerate(labels, 1)]
    return dict(
        question_id=f"{purpose}-{index}", purpose=purpose, section=section,
        prompt=prompt, instruction=INSTRUCTIONS[purpose],
        interaction_type="multipleChoice", options=options,
        correct_option_id=next(
            row["option_id"] for row in options if fold(row["label"]) == fold(correct)
        ),
        object_key=target["key"],
        prompt_translation=payload["approvedTranslations"].get(prompt),
        **extra,
    )


def _build_question(payload, purpose, section, target, prompt, answer, extra_tile, *,
                    index, **extra):
    bank = [*tokens(answer), extra_tile]
    _rng(payload, f"{purpose}-{index}").shuffle(bank)
    return dict(
        question_id=f"{purpose}-{index}", purpose=purpose, section=section,
        prompt=prompt, instruction=INSTRUCTIONS[purpose],
        interaction_type="sentenceBuilding", correct_text=answer, token_bank=bank,
        translation=payload["approvedTranslations"][answer], object_key=target["key"],
        audio_text=prompt, prompt_translation=payload["approvedTranslations"].get(prompt),
        **extra,
    )


def _sections(payload):
    focus = [_objects(payload)[key] for key in payload["focus"]]
    return [(f"Task {number} · {row['label']}", row) for number, row in enumerate(focus, 1)]


def _other(payload, target, salt):
    """Another approved object, named differently whenever the photo has one."""
    others = [row for row in payload["approvedObjects"] if row["key"] != target["key"]]
    named = [row for row in others if fold(row["noun"]) != fold(target["noun"])]
    return _rng(payload, salt).choice(named or others)


def _m01(payload):
    yes, no = payload["yesNo"]
    truths = [True, False]
    _rng(payload, "truth").shuffle(truths)
    questions = []
    for index, ((section, target), truth) in enumerate(
        zip(_sections(payload), truths, strict=True), 1,
    ):
        stated = target if truth else _other(payload, target, f"stated-{index}")
        questions += [
            _marker_question(payload, "matchName", section, target, target["name"], index=index),
            _choice_question(
                payload, "confirmName", section, target, stated["isIt"], [yes, no],
                yes if truth else no, index=index, shuffle=False,
                statement_true=truth, stated_key=stated["key"], audio_text=stated["isIt"],
            ),
            _build_question(
                payload, "buildIdentify", section, target, payload["whatIsThis"],
                target["identify"], _other(payload, target, f"tile-{index}")["noun"],
                index=index,
            ),
        ]
    return questions


def _m02(payload):
    questions = []
    for index, (section, target) in enumerate(_sections(payload), 1):
        other = _other(payload, target, f"name-{index}")
        questions += [
            _marker_question(payload, "findNamed", section, target, target["find"], index=index),
            _choice_question(
                payload, "chooseName", section, target, INSTRUCTIONS["chooseName"],
                [target["name"], other["name"]], target["name"], index=index,
            ),
            _marker_question(
                payload, "listenSelect", section, target, target["name"], index=index,
                listen_first=True,
            ),
        ]
    return questions


def _m03(payload):
    group = payload["group"]
    target = _objects(payload)[group["key"]]
    words = payload["approvedNumberWords"]
    chunks = payload["quantityChunks"]
    questions = []
    tasks = [
        ("Task 1 · Count in your photo", group["quantity"],
         dict(group_object_ids=group["objectIds"])),
        ("Task 2 · Practice board", 5 - group["quantity"],
         dict(display_count=5 - group["quantity"], board_object_id=group["boardObjectId"])),
    ]
    for index, (section, quantity, shown) in enumerate(tasks, 1):
        other = 5 - quantity
        questions += [
            _choice_question(
                payload, "countGroup", section, target, payload["howMany"],
                [words[str(number)] for number in (1, 2, 3)], words[str(quantity)],
                index=index, audio_text=payload["howMany"], **shown,
            ),
            _choice_question(
                payload, "matchChunk", section, target, INSTRUCTIONS["matchChunk"],
                [chunks[str(number)] for number in (1, 2, 3)], chunks[str(quantity)],
                index=index, **shown,
            ),
            _build_question(
                payload, "buildChunk", section, target, payload["howMany"],
                chunks[str(quantity)], tokens(words[str(other)])[0], index=index, **shown,
            ),
        ]
    return questions


def _m13(payload):
    questions = []
    for index, (section, target) in enumerate(_sections(payload), 1):
        questions += [
            _choice_question(
                payload, "chooseChunk", section, target, INSTRUCTIONS["chooseChunk"],
                [row["chunk"] for row in target["formChoices"]], target["chunk"], index=index,
            ),
            _marker_question(
                payload, "matchSpoken", section, target, target["chunk"], index=index,
            ),
            _choice_question(
                payload, "fillSlot", section, target, target["slotTemplate"],
                [row["form"] for row in target["formChoices"]], target["form"], index=index,
                slot_template=target["slotTemplate"], complete_chunk=target["chunk"],
            ),
        ]
    return questions


_BUILDERS = {"M01": _m01, "M02": _m02, "M03": _m03, "M13": _m13}


def fallback_a0_lesson(payload: dict[str, Any]) -> A0LessonResult:
    """The deterministic six-question lesson; a rebuilt lesson matches the saved one."""
    if not a0_ready(payload):
        raise LearningTaskGenerationError("The lesson needs approved, reviewed objects.")
    result = A0LessonResult.model_validate(
        dict(title=payload["title"], questions=_BUILDERS[payload["missionId"]](payload))
    )
    validate_a0_lesson(payload, result)
    return result


def a0_ready(payload: dict[str, Any]) -> bool:
    if payload["missionId"] == "M03":
        return payload.get("group") is not None
    return len(payload.get("focus") or []) == 2


def _fail(message):
    raise LearningTaskGenerationError(message)


def _check_tiles(question, approved_tokens):
    answer = Counter(map(fold, tokens(question.correct_text or "")))
    bank = Counter(map(fold, question.token_bank))
    extras = bank - answer
    if answer - bank:
        _fail("The tiles must hold every word of the answer.")
    if sum(extras.values()) != 1:
        _fail("Tile building offers exactly one extra tile.")
    if not set(bank) <= approved_tokens:
        _fail("Tiles may only use taught words.")


def validate_a0_lesson(payload: dict[str, Any], result: A0LessonResult) -> None:
    """Reject anything outside the payload's closed content or with more than one answer."""
    mission_id = payload["missionId"]
    language = payload["targetLanguage"]
    objects = _objects(payload)
    chunks = {fold(item) for item in payload["approvedSentenceChunks"]}
    forms = {fold(item) for item in payload["approvedArticlesOrEndings"]}
    approved_tokens = {fold(token) for item in payload["approvedSentenceChunks"]
                       for token in tokens(item)}
    questions = result.questions
    unique_question_ids(questions)
    if [question.purpose for question in questions] != ORDERS[mission_id] * 2:
        _fail("A0 lessons are two tasks of three questions in the mission's order.")
    first, second = questions[:3], questions[3:]
    for task in (first, second):
        if len({question.section for question in task}) != 1:
            _fail("Each task's questions share one section.")
        if len({question.object_key for question in task}) != 1:
            _fail("Each task is about one object.")
    if first[0].section == second[0].section:
        _fail("The two tasks have their own sections.")
    if mission_id == "M03":
        _validate_m03(payload, questions)
    elif first[0].object_key == second[0].object_key:
        _fail("The two tasks focus on different objects.")
    if mission_id == "M13" and language == "ko" and not forms <= set(KOREAN_ENDINGS):
        _fail("Korean uses 이에요/예요 endings, never articles.")
    for question in questions:
        target = objects.get(question.object_key)
        if target is None:
            _fail("Questions may only use approved, confirmed objects.")
        if question.instruction != INSTRUCTIONS[question.purpose]:
            _fail("Instructions are the reviewed English instructions.")
        if fold(question.prompt) not in chunks and question.prompt != INSTRUCTIONS[
            question.purpose
        ]:
            _fail("Prompts use only taught sentence chunks.")
        if question.audio_text is not None and fold(question.audio_text) not in chunks:
            _fail("Audio plays only taught sentence chunks.")
        if question.purpose in BUILD_PURPOSES:
            if question.interaction_type != "sentenceBuilding":
                _fail("Building questions use word tiles.")
            if fold(question.correct_text or "") not in chunks:
                _fail("Built answers are taught sentence chunks.")
            _check_tiles(question, approved_tokens)
            continue
        checked_answer(question)
        labels = {option.option_id: option.label for option in question.options}
        if question.purpose in MARKER_PURPOSES:
            _check_markers(question, labels, objects)
            continue
        if question.marker_keys is not None or question.accepted_option_ids:
            _fail("Only marker questions map options to objects.")
        allowed = chunks | forms | {fold(item) for item in payload["yesNo"]} | {
            fold(item) for item in payload["approvedNumberWords"].values()
        }
        if not {fold(label) for label in labels.values()} <= allowed:
            _fail("Options use only taught words and chunks.")
        if question.purpose == "confirmName":
            _validate_yes_no(payload, question, labels, objects, target)
        if question.purpose == "chooseName":
            names = {fold(row["name"]): key for key, row in objects.items()}
            if len(labels) != 2 or not all(fold(label) in names for label in labels.values()):
                _fail("Distinguish exactly two taught names.")
            if names[fold(labels[question.correct_option_id])] != target["key"]:
                _fail("The correct name is the highlighted object's.")
        if question.purpose in {"chooseChunk", "fillSlot"}:
            _validate_m13(payload, question, labels, target)


def _check_markers(question, labels, objects):
    keys = question.marker_keys or {}
    if set(keys) != set(labels) or len(set(keys.values())) != len(keys):
        _fail("Every marker option names a different approved object.")
    nouns = {}
    for option_id, key in keys.items():
        row = objects.get(key)
        if row is None or labels[option_id] != str(row["marker"]):
            _fail("Markers are approved objects with their review numbers.")
        nouns[option_id] = fold(row["noun"])
    if keys[question.correct_option_id] != question.object_key:
        _fail("The correct marker is the named object.")
    # Objects sharing the named word all answer the prompt; one with another name must not.
    named = {option_id for option_id, noun in nouns.items()
             if noun == nouns[question.correct_option_id]}
    if named != {question.correct_option_id, *question.accepted_option_ids}:
        _fail("Every marker on the named word, and only those, is accepted.")
    if len(named) == len(nouns):
        _fail("A differently named marker keeps the question a choice.")


def _validate_yes_no(payload, question, labels, objects, target):
    yes, no = payload["yesNo"]
    stated = objects.get(question.stated_key or "")
    if stated is None:
        _fail("Yes/no statements only name taught nouns.")
    if fold(question.prompt) != fold(stated["isIt"]):
        _fail("The statement names the stated object.")
    truth = fold(stated["noun"]) == fold(target["noun"])
    if question.statement_true is not truth:
        _fail("The yes/no truth value must match the photo.")
    if fold(labels[question.correct_option_id]) != fold(yes if truth else no):
        _fail("The answer must match the statement's truth.")


def _validate_m13(payload, question, labels, target):
    language = payload["targetLanguage"]
    allowed = {fold(row["form"]) for row in target["formChoices"]}
    if not payload["pluralsTaught"] and any(row["plural"] for row in target["formChoices"]):
        _fail("Plural forms appear only after plurals are taught.")
    if question.purpose == "fillSlot":
        if not {fold(label) for label in labels.values()} <= allowed:
            _fail("Slot options are reviewed forms for the noun.")
        if fold(labels[question.correct_option_id]) != fold(target["form"]):
            _fail("The slot answer is the noun's reviewed form.")
        if question.slot_template != target["slotTemplate"] or SLOT not in question.prompt:
            _fail("The slot template leaves only the form missing.")
        if language == "ko" and not set(labels.values()) <= set(KOREAN_ENDINGS):
            _fail("Korean slots choose 이에요 or 예요.")
        return
    by_chunk = {fold(row["chunk"]): row for row in target["formChoices"]}
    if not {fold(label) for label in labels.values()} <= set(by_chunk):
        _fail("Chunk options differ from the answer in the form only.")
    if fold(labels[question.correct_option_id]) != fold(target["chunk"]):
        _fail("The correct chunk uses the noun's reviewed form.")


def _validate_m03(payload, questions):
    group = payload["group"]
    if group is None or group["quantity"] not in (2, 3):
        _fail("The lesson needs one learner-counted group of 2 or 3.")
    if group["quantity"] != group["confirmedQuantity"]:
        _fail("The learner's count must never be changed.")
    words = payload["approvedNumberWords"]
    chunks = payload["quantityChunks"]
    for index, question in enumerate(questions):
        if question.object_key != group["key"]:
            _fail("Every question is about the counted group.")
        expected = group["quantity"] if index < 3 else 5 - group["quantity"]
        if index >= 3 and question.display_count != expected:
            _fail("The practice board shows the other small number.")
        if index < 3 and (question.display_count is not None
                          or question.group_object_ids != group["objectIds"]):
            _fail("Task 1 highlights the counted group in the photo.")
        shown = [question.prompt, *(option.label for option in question.options)]
        if any(_DIGIT.search(text) for text in shown):
            _fail("Counts are shown as number words, never numerals.")
        if question.purpose == "buildChunk":
            if fold(question.correct_text or "") != fold(chunks[str(expected)]):
                _fail("The built chunk matches the count.")
            continue
        labels = {option.option_id: option.label for option in question.options}
        answer = words[str(expected)] if question.purpose == "countGroup" else chunks[
            str(expected)
        ]
        if fold(labels.get(question.correct_option_id or "", "")) != fold(answer):
            _fail("The answer must match the count.")


def _generation(mission_id):
    return MissionGeneration(
        prompt_version=f"learning-tasks.{mission_id.lower()}-a0.v1",
        schema_version=A0_SCHEMA_VERSION,
        validator_version=A0_VALIDATOR_VERSION,
        system_prompt="A0 lessons are built deterministically from reviewed content.",
        result_model=A0LessonResult,
        validate=validate_a0_lesson,
        fallback=fallback_a0_lesson,
        json_schema_name=f"{mission_id.lower()}_a0_lesson_v1",
        uses_model=False,
    )


A0_GENERATIONS = {mission_id: _generation(mission_id) for mission_id in ORDERS}
