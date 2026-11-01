"""M03 A1 mission lesson: say how many of an object there are.

The lesson is built deterministically from the learner-counted group, the taught
number range and reviewed plurals, and accepted only through
``validate_m03_lesson``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.schemas.base import ApiModel, NonEmptyText

type M03Purpose = Literal["chooseQuantity", "buildQuantity", "matchQuantity"]

_INTERACTIONS = {
    "chooseQuantity": "multipleChoice",
    "buildQuantity": "sentenceBuilding",
    "matchQuantity": "multipleChoice",
}
SECTION_PHOTO = "Task 1 · Count in your photo"
SECTION_BOARD = "Task 2 · Practice board"


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




def nearby_quantities(number, taught, *, skip_first=False):
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














