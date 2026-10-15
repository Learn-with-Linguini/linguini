"""M02 A1 mission lesson: say where an object is, ask where it is and understand the answer.

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

M02_PROMPT_VERSION = "learning-tasks.m02-a1.v2"
M02_SCHEMA_VERSION = "learning-tasks-m02-result.v2"
M02_VALIDATOR_VERSION = "learning-tasks-m02-validator.v2"

type M02Purpose = Literal["choosePosition", "describeLocation", "askWhere", "understandAnswer"]

_ORDER: list[M02Purpose] = ["choosePosition", "describeLocation", "askWhere", "understandAnswer"]
_INTERACTIONS = {
    "choosePosition": "multipleChoice",
    "describeLocation": "sentenceBuilding",
    "askWhere": "sentenceBuilding",
    "understandAnswer": "multipleChoice",
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
    explanation: NonEmptyText = Field(max_length=400)
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
    """Check confirmed-fact references, the fixed four-part order and single answers."""
    relations = {row["key"]: row for row in payload["relations"]}
    questions = result.questions
    unique_question_ids(questions)
    if [question.purpose for question in questions] != _ORDER:
        raise LearningTaskGenerationError("Parts go: position, statement, question, answer.")
    first, second = (relations.get(questions[index].relation_key) for index in (0, 2))
    if first is None or second is None:
        raise LearningTaskGenerationError("Every part must use a confirmed relation.")
    if questions[1].relation_key != first["key"] or questions[3].relation_key != second["key"]:
        raise LearningTaskGenerationError("Both parts of a task use the same relation.")
    for question, relation in zip(questions, [first, first, second, second], strict=True):
        if question.object_key != relation["subjectKey"]:
            raise LearningTaskGenerationError("Questions must be about the relation's object.")
    choose, describe, ask, understand = questions
    labels = _choices(choose)
    phrases = {row["position"]: row["expression"] for row in payload["positions"]}
    true_for_pair = set(first["truePositions"])
    if fold(labels[choose.correct_option_id]) != fold(first["expression"]):
        raise LearningTaskGenerationError("The correct phrase must be the confirmed position.")
    offered = {fold(text): position for position, text in phrases.items()}
    for option_id, label in labels.items():
        position = offered.get(fold(label))
        if position is None:
            raise LearningTaskGenerationError("Phrases must be reviewed positions.")
        if option_id != choose.correct_option_id and position in true_for_pair:
            raise LearningTaskGenerationError("Only one phrase may match the photo.")
    _check_tiles(describe, first["statementTiles"], [first["extraTile"]])
    if fold(ask.correct_text or "") != fold(second["whereQuestion"]):
        raise LearningTaskGenerationError("The question must be the reviewed where-question.")
    checked_answer(ask)
    labels = _choices(understand)
    if understand.correct_option_id != second["position"] or fold(second["answer"]) not in fold(
        understand.prompt
    ):
        raise LearningTaskGenerationError("The answer must quote the confirmed relation.")
    wrong = set(labels) - {second["position"]}
    if not wrong <= set(phrases) or wrong & set(second["truePositions"]):
        raise LearningTaskGenerationError("Diagram options must show other positions only.")


def _relation_choices(relation, positions):
    """The confirmed position and up to two reviewed positions untrue for the pair."""
    others = [row for row in positions if row["position"] not in relation["truePositions"]]
    return [relation["position"], *[row["position"] for row in others[:2]]]


def fallback_m02_lesson(payload: dict[str, Any]) -> M02LessonResult:
    """The four-part lesson from the selected relations; it passes the same validator."""
    if len(payload["relations"]) < 1 or len(payload["selected"]) != 2:
        raise LearningTaskGenerationError("The lesson needs a confirmed relation.")
    relations = {row["key"]: row for row in payload["relations"]}
    first, second = (relations[key] for key in payload["selected"])
    phrases = {row["position"]: row for row in payload["positions"]}
    shown = _relation_choices(first, payload["positions"])
    order = sorted(shown, key=lambda position: fold(phrases[position]["expression"]))
    describe_bank = [*first["statementTiles"], first["extraTile"]]
    understand = _relation_choices(second, payload["positions"])
    questions = [
        dict(
            question_id="choose-position", purpose="choosePosition",
            prompt=f"Where is the {first['subjectSource']} in relation to the "
            f"{first['referenceSource']}?",
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
            prompt=f"Describe where the {first['subjectSource']} is.",
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=first["statement"],
            token_bank=sorted(describe_bank, key=fold),
            translation=f"Say where the {first['subjectSource']} is.",
            object_key=first["subjectKey"], relation_key=first["key"],
        ),
        dict(
            question_id="ask-where", purpose="askWhere",
            prompt=f"Ask where the {second['subjectSource']} is.",
            interaction_type="sentenceBuilding", options=[], correct_option_id=None,
            correct_text=second["whereQuestion"],
            token_bank=list(reversed(tokens(second["whereQuestion"]))),
            translation=f"Where is the {second['subjectSource']}?",
            object_key=second["subjectKey"], relation_key=second["key"],
        ),
        dict(
            question_id="understand-answer", purpose="understandAnswer",
            prompt=f"\u201c{second['answer']}\u201d Which picture shows this?",
            interaction_type="multipleChoice",
            options=[
                dict(
                    option_id=position,
                    label=f"The {second['subjectSource']} is {phrases[position]['meaning']} "
                    f"the {second['referenceSource']}.",
                )
                for position in sorted(understand)
            ],
            correct_option_id=second["position"],
            correct_text=None, token_bank=[], translation=None,
            object_key=second["subjectKey"], relation_key=second["key"],
        ),
    ]
    taught = "; ".join(
        f"\u201c{phrases[position]['expression']}\u201d = {phrases[position]['meaning']}"
        for position in order
    )
    result = M02LessonResult.model_validate(dict(
        title="Find and locate",
        explanation=f"Say where something is with a position phrase: {taught}.",
        questions=questions,
    ))
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
    "mission_lesson_m02_v2",
    uses_model=False,
)
