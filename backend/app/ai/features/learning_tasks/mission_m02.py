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

M02_PROMPT_VERSION = "learning-tasks.m02-a1.v4"
M02_SCHEMA_VERSION = "learning-tasks-m02-result.v4"
M02_VALIDATOR_VERSION = "learning-tasks-m02-validator.v4"

type M02Purpose = Literal["findObject", "chooseLocation", "askWhere", "answerWhere"]

FIND_SECTION = "Task 1 · Find it in your photo"
ASK_SECTION = "Task 2 · Ask and answer where"
_ORDER: list[M02Purpose] = ["findObject", "chooseLocation", "askWhere", "answerWhere"]
_INTERACTIONS = {
    "findObject": "multipleChoice",
    "chooseLocation": "multipleChoice",
    "askWhere": "sentenceBuilding",
    "answerWhere": "sentenceBuilding",
}
_SECTIONS = {
    "findObject": FIND_SECTION,
    "chooseLocation": FIND_SECTION,
    "askWhere": ASK_SECTION,
    "answerWhere": ASK_SECTION,
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


def _choices(question):
    labels = {option.option_id: option.label for option in question.options}
    if len(labels) != len(question.options) or len(labels) < 2:
        raise LearningTaskGenerationError("Choices need 2-4 uniquely identified options.")
    if question.correct_option_id not in labels:
        raise LearningTaskGenerationError("The correct option must be offered.")
    return labels


def _check_tiles(question, tiles, extras):
    if question.options or question.correct_option_id is not None:
        raise LearningTaskGenerationError("Sentence building cannot offer options.")
    if fold(question.correct_text or "") != fold(_joined(tiles)):
        raise LearningTaskGenerationError("The answer must be the reviewed sentence.")
    if Counter(question.token_bank) != Counter([*tiles, *extras]):
        raise LearningTaskGenerationError("The tiles must hold exactly the answer and its extras.")


def _joined(tiles):
    text = ""
    for tile in tiles:
        joins = tile in {".", ",", "?", "!"} or text.endswith("'")
        text = f"{text}{'' if joins or not text else ' '}{tile}"
    return text


def validate_m02_lesson(payload: dict[str, Any], result: M02LessonResult) -> None:
    """Four questions on one confirmed relation; every answer is a confirmed fact."""
    relations = {row["key"]: row for row in payload["relations"]}
    questions = result.questions
    unique_question_ids(questions)
    if [question.purpose for question in questions] != _ORDER:
        raise LearningTaskGenerationError("Questions go: find, locate, ask, answer.")
    if len(payload["selected"]) != 1 or payload["selected"][0] not in relations:
        raise LearningTaskGenerationError("The lesson uses one confirmed relation.")
    relation = relations[payload["selected"][0]]
    for question in questions:
        same = (question.relation_key, question.object_key)
        if same != (relation["key"], relation["subjectKey"]):
            raise LearningTaskGenerationError("Every question uses the same relation.")
        if question.section != _SECTIONS[question.purpose]:
            raise LearningTaskGenerationError("Questions belong to their task.")
        if question.interaction_type == "multipleChoice" and question.translation:
            raise LearningTaskGenerationError("Choices never reveal a translation.")
    find, choose, ask, answer = questions

    labels = _choices(find)
    markers = {row["key"]: row for row in payload["markers"]}
    if fold(find.prompt) != fold(relation["statement"]):
        raise LearningTaskGenerationError("The clue is the confirmed statement.")
    if set(find.marker_keys or {}) != set(labels):
        raise LearningTaskGenerationError("Every marker option names one scene object.")
    if len(set(find.marker_keys.values())) != len(labels):
        raise LearningTaskGenerationError("Marker options are different objects.")
    for option_id, key in find.marker_keys.items():
        marker = markers.get(key)
        if marker is None or labels[option_id] != str(marker["marker"]):
            raise LearningTaskGenerationError("Markers are confirmed objects with their numbers.")
        if option_id != find.correct_option_id and fold(marker["source"]) == fold(
            relation["subjectSource"]
        ):
            raise LearningTaskGenerationError("Only one marker may match the clue.")
    if find.marker_keys[find.correct_option_id] != relation["subjectKey"]:
        raise LearningTaskGenerationError("The correct marker is the relation's object.")

    labels = _choices(choose)
    places = {fold(row["label"]): row["position"] for row in relation["placeOptions"]}
    if fold(choose.prompt) != fold(relation["whereQuestion"]):
        raise LearningTaskGenerationError("The location question asks where the object is.")
    if places.get(fold(labels[choose.correct_option_id])) != relation["position"]:
        raise LearningTaskGenerationError("The correct place is the confirmed position.")
    for option_id, label in labels.items():
        position = places.get(fold(label))
        if position is None:
            raise LearningTaskGenerationError("Places must be reviewed positions.")
        if option_id != choose.correct_option_id and position in relation["truePositions"]:
            raise LearningTaskGenerationError("Only one place may match the photo.")

    if fold(ask.correct_text or "") != fold(relation["whereQuestion"]):
        raise LearningTaskGenerationError("The question must be the reviewed where-question.")
    checked_answer(ask)
    _check_tiles(answer, relation["statementTiles"], [relation["answerExtra"]])


def fallback_m02_lesson(payload: dict[str, Any]) -> M02LessonResult:
    """The deterministic four-question lesson on the selected relation.

    Marker options keep their photo numbers in order; place options follow the
    session-seeded order in the payload, so a rebuilt lesson matches the saved one.
    """
    if len(payload["selected"]) != 1:
        raise LearningTaskGenerationError("The lesson needs a confirmed relation.")
    relation = next(row for row in payload["relations"] if row["key"] == payload["selected"][0])
    markers = {row["key"]: row for row in payload["markers"]}
    shown = sorted(relation["markerOptions"], key=lambda key: markers[key]["marker"])
    find_options = [
        dict(option_id=f"marker-{markers[key]['marker']}", label=str(markers[key]["marker"]))
        for key in shown
    ]
    places = [relation["placeOptions"][index] for index in relation["placeOrder"]]
    place_options = [
        dict(option_id=f"place-{index}", label=row["label"]) for index, row in enumerate(places, 1)
    ]
    common = dict(object_key=relation["subjectKey"], relation_key=relation["key"])
    choice = dict(correct_text=None, token_bank=[], translation=None, **common)
    questions = [
        dict(
            choice, question_id="find-object", purpose="findObject", section=FIND_SECTION,
            prompt=relation["statement"], interaction_type="multipleChoice",
            options=find_options,
            correct_option_id=f"marker-{markers[relation['subjectKey']]['marker']}",
            marker_keys={
                item["option_id"]: key for item, key in zip(find_options, shown, strict=True)
            },
        ),
        dict(
            choice, question_id="choose-location", purpose="chooseLocation",
            section=FIND_SECTION, prompt=relation["whereQuestion"],
            interaction_type="multipleChoice", options=place_options,
            correct_option_id=next(
                item["option_id"] for item, row in zip(place_options, places, strict=True)
                if row["position"] == relation["position"]
            ),
        ),
        dict(
            question_id="ask-where", purpose="askWhere", section=ASK_SECTION,
            prompt=relation["prompts"]["askWhere"],
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=relation["whereQuestion"],
            token_bank=list(reversed(tokens(relation["whereQuestion"]))),
            translation=f"Where is the {relation['subjectSource']}?", **common,
        ),
        dict(
            question_id="answer-where", purpose="answerWhere", section=ASK_SECTION,
            prompt=relation["prompts"]["answerWhere"],
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=relation["statement"],
            token_bank=sorted([*relation["statementTiles"], relation["answerExtra"]], key=fold),
            translation=(
                f"The {relation['subjectSource']} is {relation['meaning']} "
                f"the {relation['referenceSource']}."
            ),
            **common,
        ),
    ]
    result = M02LessonResult.model_validate(dict(title="Find and locate", questions=questions))
    validate_m02_lesson(payload, result)
    return result


M02_GENERATION = MissionGeneration(
    M02_PROMPT_VERSION,
    M02_SCHEMA_VERSION,
    M02_VALIDATOR_VERSION,
    "",
    M02LessonResult,
    validate_m02_lesson,
    fallback_m02_lesson,
    "mission_lesson_m02_v4",
    uses_model=False,
)
