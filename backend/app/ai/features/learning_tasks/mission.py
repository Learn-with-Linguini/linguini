"""Shared mission lesson generation spec and answer checks."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel

_TOKEN = re.compile(r"[^\s.,!?;:'’]+['’]?|[.,!?;:]")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def fold(value: str) -> str:
    return " ".join(value.replace("’", "'").casefold().split())


def checked_answer(question: Any) -> str:
    """The folded correct answer once the interaction's shape is answerable."""
    if question.interaction_type == "multipleChoice":
        labels = {option.option_id: option.label for option in question.options}
        if len(labels) != len(question.options) or len(question.options) < 2:
            raise LearningTaskGenerationError(
                "Multiple choice needs 2-4 uniquely identified options."
            )
        if len({fold(label) for label in labels.values()}) != len(labels):
            raise LearningTaskGenerationError("Multiple-choice options must be distinct.")
        if question.correct_option_id not in labels:
            raise LearningTaskGenerationError("The correct option must be offered.")
        if question.correct_text is not None or question.token_bank:
            raise LearningTaskGenerationError("Multiple choice cannot carry a word bank.")
        return fold(labels[question.correct_option_id])
    if question.options or question.correct_option_id is not None:
        raise LearningTaskGenerationError("Sentence building cannot offer options.")
    if not (question.translation or "").strip() or not question.correct_text:
        raise LearningTaskGenerationError("Sentence building needs a sentence and translation.")
    if Counter(map(fold, question.token_bank)) != Counter(map(fold, tokens(question.correct_text))):
        raise LearningTaskGenerationError("The word bank must hold exactly the answer's tokens.")
    return fold(question.correct_text)


def unique_question_ids(questions: list[Any]) -> None:
    if len({question.question_id for question in questions}) != len(questions):
        raise LearningTaskGenerationError("Question ids must be unique within the lesson.")


@dataclass(frozen=True)
class MissionGeneration:
    """Prompt, schema, validator and fallback that generate one mission's lesson."""

    prompt_version: str
    schema_version: str
    validator_version: str
    system_prompt: str
    result_model: type[ApiModel]
    validate: Callable[[dict[str, Any], Any], Any]
    fallback: Callable[[dict[str, Any]], Any]
    json_schema_name: str
    uses_model: bool = True
    # Replaces the grammar-task repair note on a validation retry when set.
    repair_instruction: str | None = None
