"""Closed, deterministic A0 ownership and preference lessons."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field

from app.ai.features.learning_tasks.mission import MissionGeneration, fold
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel, NonEmptyText


class SituationOption(ApiModel):
    option_id: NonEmptyText
    label: NonEmptyText


class SituationQuestion(ApiModel):
    question_id: NonEmptyText
    prompt: NonEmptyText
    instruction: NonEmptyText
    section: NonEmptyText
    gap_type: Literal[
        "chunkChoice", "pictureToBlank", "audioGap", "dialogueGap",
    ] | None = None
    options: Annotated[list[SituationOption], Field(min_length=2, max_length=3)]
    correct_option_id: NonEmptyText
    object_key: NonEmptyText
    marker_keys: dict[str, str] | None = None
    option_object_keys: dict[str, str] | None = None
    option_icons: dict[str, Literal["belongs", "likes", "like", "dislike"]] | None = None
    audio_text: str | None = None
    listen_first: bool = False
    slot_template: str | None = None
    complete_chunk: str | None = None
    complete_translation: str | None = None
    dialogue: list[dict[str, str]] | None = None
    correct_note: str | None = None
    outcome: dict[str, str] | None = None
    typed_allowed: bool = False
    accepted_text_answers: list[str] = Field(default_factory=list)
    target_group: Literal[
        "recognise-ownership", "say-mine", "recognise-preference", "say-preference",
    ]


class A0SituationLesson(ApiModel):
    title: NonEmptyText
    questions: Annotated[list[SituationQuestion], Field(min_length=6, max_length=6)]


_ORDER = {
    "M04": [None, None, "chunkChoice", "chunkChoice", "audioGap", "dialogueGap"],
    "M05": [None, None, "chunkChoice", "pictureToBlank", "dialogueGap", "dialogueGap"],
}
_GRAMMAR_WORDS = re.compile(
    (
        r"\b(?:possessive|pronoun|first person|negation|negative|particle|article|gender|"
        r"conjugat\w*)\b"
    ),
    re.IGNORECASE,
)


def validate_a0_situation_lesson(payload: dict[str, Any], result: A0SituationLesson) -> None:
    """Reject any lesson that does not follow the reviewed, fact-bound content."""
    mission_id = payload.get("missionId")
    if mission_id not in _ORDER:
        raise LearningTaskGenerationError("Unknown A0 situation mission.")
    questions = result.questions
    if [question.gap_type for question in questions] != _ORDER[mission_id]:
        raise LearningTaskGenerationError("A0 situation question order is invalid.")
    if sum(question.gap_type is not None for question in questions) < 3:
        raise LearningTaskGenerationError("A0 situation lessons need at least three gaps.")
    objects = {str(row["key"]): row for row in payload.get("approvedObjects", [])}
    if len(objects) < 2:
        raise LearningTaskGenerationError("A0 situations need two reviewed objects.")
    facts = payload.get("learnerFacts") or {}
    if mission_id == "M04":
        focus_key = str(facts.get("ownedObjectId") or "")
        if focus_key not in objects:
            raise LearningTaskGenerationError("Ownership must name a reviewed object.")
    else:
        preference = facts.get("preference") or facts
        compared = [str(item) for item in preference.get("sceneObjectIds", [])]
        focus_key = str(
            preference.get("chosenObjectId") if len(compared) == 2 else
            compared[0] if compared else ""
        )
        if focus_key not in objects or preference.get("reaction") not in {"like", "dislike"}:
            raise LearningTaskGenerationError(
                "Preference must name a reviewed object and reaction."
            )

    prep = {fold(item["text"]) for item in payload.get("prep", [])}
    approved = {fold(item) for item in payload.get("approvedTargetTexts", [])}
    previous_phrases = set(prep)
    target_language = payload.get("targetLanguage")
    for index, question in enumerate(questions):
        option_ids = [option.option_id for option in question.options]
        option_labels = [fold(option.label) for option in question.options]
        if len(set(option_ids)) != len(option_ids) or len(set(option_labels)) != len(option_labels):
            raise LearningTaskGenerationError("A0 situation options must be unique.")
        if question.correct_option_id not in option_ids:
            raise LearningTaskGenerationError("A0 situation answers must be offered.")
        if question.gap_type and (
            not question.slot_template or question.slot_template.count("___") != 1
            or not question.complete_chunk or fold(question.complete_chunk) not in prep
        ):
            raise LearningTaskGenerationError("A0 situation gaps need a prepared completion.")
        if question.marker_keys and (
            set(question.marker_keys) != set(option_ids)
            or question.marker_keys.get(question.correct_option_id) != focus_key
        ):
            raise LearningTaskGenerationError("A0 situation marker answer disagrees with the fact.")
        if question.option_object_keys and set(question.option_object_keys) != set(option_ids):
            raise LearningTaskGenerationError("Picture choices must map every option.")
        if question.gap_type == "pictureToBlank" and (
            not question.option_object_keys
            or question.option_object_keys.get(question.correct_option_id) != focus_key
        ):
            raise LearningTaskGenerationError("The picture answer disagrees with the preference.")
        target_labels = question.options
        if index == 0:
            target_labels = []
        elif index == 1:
            target_labels = []
        if any(fold(option.label) not in approved for option in target_labels):
            raise LearningTaskGenerationError("A0 situation option is not an approved chunk.")
        for text in (
            question.audio_text, question.slot_template, question.complete_chunk,
            *(turn["text"] for turn in question.dialogue or []),
        ):
            if text and fold(text) not in approved:
                raise LearningTaskGenerationError("A0 situation text is not an approved chunk.")
        if question.gap_type == "audioGap" and (
            fold(question.audio_text or "") not in previous_phrases
        ):
            raise LearningTaskGenerationError("Audio gaps must follow a taught phrase.")
        if question.gap_type == "audioGap" and not question.listen_first:
            raise LearningTaskGenerationError("Audio gaps must start with listening.")
        if question.gap_type and question.correct_option_id not in option_ids:
            raise LearningTaskGenerationError("A0 situation gaps need a correct option.")
        if question.typed_allowed and target_language == "ko":
            raise LearningTaskGenerationError("Korean situation gaps cannot be typed.")
        english = [
            question.prompt, question.instruction, question.complete_translation or "",
            question.correct_note or "", (question.outcome or {}).get("text", ""),
            *(turn.get("translation", "") for turn in question.dialogue or []),
        ]
        if any(_GRAMMAR_WORDS.search(text) for text in english):
            raise LearningTaskGenerationError("A0 situation English must stay learner-friendly.")
        previous_phrases.add(fold(question.complete_chunk or ""))

    if mission_id == "M05":
        preference = facts.get("preference") or facts
        reaction = preference.get("reaction")
        question_two_answer = next(
            option.label for option in questions[1].options
            if option.option_id == questions[1].correct_option_id
        )
        question_three_answer = next(
            option.label for option in questions[2].options
            if option.option_id == questions[2].correct_option_id
        )
        expected_question_two = "Like" if reaction == "like" else "Don't like"
        question_three_complete = fold(questions[2].complete_chunk or "")
        negative_markers = {
            "es": "no me gusta",
            "fr": "je n'aime pas",
            "de": "nicht",
            "ko": "안 좋아해요",
        }
        is_negative = negative_markers[target_language] in question_three_complete
        if (
            question_two_answer != expected_question_two
            or fold(question_three_answer) not in question_three_complete
            or is_negative != (reaction == "dislike")
        ):
            raise LearningTaskGenerationError(
                "Preference answers disagree with the learner's choice."
            )


def _fallback(payload: dict[str, Any]) -> A0SituationLesson:
    from app.services.mission_lessons_a0_situations import build_a0_situation_lesson

    result = build_a0_situation_lesson(payload)
    validate_a0_situation_lesson(payload, result)
    return result


def _validate(payload: dict[str, Any], result: A0SituationLesson) -> None:
    validate_a0_situation_lesson(payload, result)


_GENERATION = {
    mission_id: MissionGeneration(
        prompt_version=f"a0-situation-{mission_id.lower()}-v1",
        schema_version="a0-situation-result.v1",
        validator_version="a0-situation-validator.v1",
        system_prompt="",
        result_model=A0SituationLesson,
        validate=_validate,
        fallback=_fallback,
        json_schema_name=f"a0_situation_{mission_id.lower()}",
        uses_model=False,
    )
    for mission_id in _ORDER
}
A0_SITUATION_GENERATIONS = _GENERATION
