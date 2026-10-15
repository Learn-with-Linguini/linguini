"""M02 A1 mission lesson: say where an object is, ask where it is and check an answer.

The lesson is built deterministically from learner-confirmed objects and relations with
reviewed target-language forms, and accepted only through ``validate_m02_lesson``.
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

M02_PROMPT_VERSION = "learning-tasks.m02-a1.v3"
M02_SCHEMA_VERSION = "learning-tasks-m02-result.v3"
M02_VALIDATOR_VERSION = "learning-tasks-m02-validator.v3"

type M02Purpose = Literal["choosePosition", "describeLocation", "askWhere", "checkAnswer"]

_CORE: list[M02Purpose] = ["choosePosition", "describeLocation", "askWhere"]
_INTERACTIONS = {
    "choosePosition": "multipleChoice",
    "describeLocation": "sentenceBuilding",
    "askWhere": "sentenceBuilding",
    "checkAnswer": "multipleChoice",
}


class M02Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: M02Purpose
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)]
    correct_option_id: Annotated[str, Field(max_length=64)] | None
    correct_text: Annotated[str, Field(max_length=300)] | None
    token_bank: Annotated[list[Annotated[NonEmptyText, Field(max_length=40)]], Field(max_length=20)]
    translation: Annotated[str, Field(max_length=300)] | None
    object_key: NonEmptyText = Field(max_length=200)
    relation_key: NonEmptyText = Field(max_length=200)

    @model_validator(mode="after")
    def validate_interaction(self) -> M02Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError(f"{self.purpose} questions use {_INTERACTIONS[self.purpose]}")
        return self


class M02LessonResult(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[M02Question], Field(min_length=3, max_length=4)]


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


def _validate_check(payload, question, first, second):
    if second is None or second["key"] == first["key"]:
        raise LearningTaskGenerationError("The answer check needs another confirmed relation.")
    if question.object_key != second["subjectKey"]:
        raise LearningTaskGenerationError("Questions must be about the relation's object.")
    labels = _choices(question)
    if set(labels) != {"yes", "no"}:
        raise LearningTaskGenerationError("The answer check offers yes and no.")
    check = second["check"]
    if fold(check["proposal"]) not in fold(question.prompt):
        raise LearningTaskGenerationError("The answer check must quote its proposed answer.")
    matches = check["position"] in second["truePositions"]
    if not matches and check["position"] not in second["contradicted"]:
        raise LearningTaskGenerationError("A wrong proposal must contradict the photo.")
    if question.correct_option_id != ("yes" if matches else "no"):
        raise LearningTaskGenerationError("The answer check key must match the photo.")


def validate_m02_lesson(payload: dict[str, Any], result: M02LessonResult) -> None:
    """Check confirmed-fact references, the core order, the optional check and single answers."""
    relations = {row["key"]: row for row in payload["relations"]}
    questions = result.questions
    unique_question_ids(questions)
    extra = [question.purpose for question in questions[3:]]
    if [question.purpose for question in questions[:3]] != _CORE or extra not in ([], [
        "checkAnswer"
    ]):
        raise LearningTaskGenerationError("Questions go: position, statement, question, check.")
    if bool(extra) != (len(payload["selected"]) == 2):
        raise LearningTaskGenerationError("Add the answer check only for a second relation.")
    first = relations.get(questions[0].relation_key)
    if first is None:
        raise LearningTaskGenerationError("Every question must use a confirmed relation.")
    for question in questions[:3]:
        if question.relation_key != first["key"] or question.object_key != first["subjectKey"]:
            raise LearningTaskGenerationError("The core questions use the same relation.")
    choose, describe, ask = questions[:3]
    labels = _choices(choose)
    phrases = {row["position"]: row["expression"] for row in payload["positions"]}
    if fold(labels[choose.correct_option_id]) != fold(first["expression"]):
        raise LearningTaskGenerationError("The correct phrase must be the confirmed position.")
    offered = {fold(text): position for position, text in phrases.items()}
    for option_id, label in labels.items():
        position = offered.get(fold(label))
        if position is None:
            raise LearningTaskGenerationError("Phrases must be reviewed positions.")
        if option_id != choose.correct_option_id and position in first["truePositions"]:
            raise LearningTaskGenerationError("Only one phrase may match the photo.")
    _check_tiles(describe, first["statementTiles"], [first["extraTile"]])
    if fold(ask.correct_text or "") != fold(first["whereQuestion"]):
        raise LearningTaskGenerationError("The question must be the reviewed where-question.")
    checked_answer(ask)
    if extra:
        _validate_check(payload, questions[3], first, relations.get(questions[3].relation_key))


def _relation_choices(relation, positions):
    """The confirmed position and up to two reviewed positions untrue for the pair."""
    others = [row for row in positions if row["position"] not in relation["truePositions"]]
    return [relation["position"], *[row["position"] for row in others[:2]]]


def fallback_m02_lesson(payload: dict[str, Any]) -> M02LessonResult:
    """Three core questions, plus the answer check when a second relation was selected."""
    if not payload["selected"]:
        raise LearningTaskGenerationError("The lesson needs a confirmed relation.")
    relations = {row["key"]: row for row in payload["relations"]}
    first = relations[payload["selected"][0]]
    phrases = {row["position"]: row for row in payload["positions"]}
    shown = _relation_choices(first, payload["positions"])
    order = sorted(shown, key=lambda position: fold(phrases[position]["expression"]))
    describe_bank = [*first["statementTiles"], first["extraTile"]]
    questions = [
        dict(
            question_id="choose-position", purpose="choosePosition",
            prompt=first["prompts"]["choosePosition"],
            interaction_type="multipleChoice",
            options=[
                dict(option_id=f"phrase-{index}", label=phrases[position]["expression"])
                for index, position in enumerate(order, 1)
            ],
            correct_option_id=f"phrase-{order.index(first['position']) + 1}",
            correct_text=None, token_bank=[], translation=None,
            object_key=first["subjectKey"], relation_key=first["key"],
        ),
        dict(
            question_id="describe-location", purpose="describeLocation",
            prompt=first["prompts"]["describeLocation"],
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=first["statement"],
            token_bank=sorted(describe_bank, key=fold),
            translation=f"Say where the {first['subjectSource']} is.",
            object_key=first["subjectKey"], relation_key=first["key"],
        ),
        dict(
            question_id="ask-where", purpose="askWhere",
            prompt=first["prompts"]["askWhere"],
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=first["whereQuestion"],
            token_bank=list(reversed(tokens(first["whereQuestion"]))),
            translation=f"Where is the {first['subjectSource']}?",
            object_key=first["subjectKey"], relation_key=first["key"],
        ),
    ]
    if len(payload["selected"]) == 2:
        second = relations[payload["selected"][1]]
        matches = second["check"]["position"] in second["truePositions"]
        questions.append(dict(
            question_id="check-answer", purpose="checkAnswer",
            prompt=second["prompts"]["checkAnswer"],
            interaction_type="multipleChoice",
            options=[
                dict(option_id=key, label=label) for key, label in payload["yesNo"].items()
            ],
            correct_option_id="yes" if matches else "no",
            correct_text=None, token_bank=[], translation=None,
            object_key=second["subjectKey"], relation_key=second["key"],
        ))
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
    "mission_lesson_m02_v3",
    uses_model=False,
)
