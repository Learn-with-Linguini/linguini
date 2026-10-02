"""Ground-truth case format for the scene-analysis evaluation dataset.

A case pairs one image with what a *good* answer looks like. Scene analysis has
no single correct answer: a classroom photo may reasonably yield
``desk, chair, globe`` or ``desk, chair, bookshelf`` and both are fine. So a
case never encodes one exact expected payload. It encodes four things:

``anchors``
    Objects a competent model must find. Missing one is a real miss.
    Scored as recall. Keep this set small -- the prompt caps output at six
    objects, so demanding more than three or four anchors punishes a model for
    obeying the prompt.

``acceptable``
    The wider pool of objects genuinely present in the photo. Anything the
    model returns that is neither an anchor nor acceptable is counted as an
    unsupported detection. Scored as precision.

``forbidden``
    Hard rule violations -- people, brands, and anything the prompt bans.
    These are not "wrong answers", they are safety failures, and are reported
    separately from accuracy so one never hides the other.

``expectation mode``
    ``objects`` for a normal photo, ``empty`` for an image so degraded that the
    correct behaviour is returning an empty ``objects`` array rather than
    guessing.

Labels are matched through ``accept`` alias lists, case-insensitively, because
"bin"/"trash can"/"rubbish bin" are the same answer for vocabulary purposes.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ExpectationMode(StrEnum):
    OBJECTS = "objects"
    EMPTY = "empty"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    UNUSABLE = "unusable"


class CaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Box(CaseModel):
    """Normalized reference box, same convention as the prompt: top-left origin."""

    x: Annotated[float, Field(ge=0, le=1)]
    y: Annotated[float, Field(ge=0, le=1)]
    width: Annotated[float, Field(gt=0, le=1)]
    height: Annotated[float, Field(gt=0, le=1)]

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)


class ExpectedObject(CaseModel):
    """One object we expect to be findable in the image."""

    canonical: str
    accept: list[str] = []
    box: Box | None = None
    note: str | None = None

    def aliases(self) -> set[str]:
        return {alias.strip().casefold() for alias in [self.canonical, *self.accept]}


class ExpectedRelation(CaseModel):
    """A spatial relation that is unambiguously true in the image.

    Subject and reference name *canonical labels*, not object keys -- keys are
    assigned by the model at runtime and carry no meaning across responses.
    """

    subject: str
    relation: str
    reference: str
    note: str | None = None


class Expectation(CaseModel):
    mode: ExpectationMode = ExpectationMode.OBJECTS
    scene_title_accept: list[str] = []
    anchors: list[ExpectedObject] = []
    acceptable: list[ExpectedObject] = []
    relations: list[ExpectedRelation] = []
    forbidden_labels: list[str] = []
    min_objects: int = 3
    max_objects: int = 6
    max_confidence: float | None = None
    """For degraded images: every confidenceScore should sit at or below this."""


class EvalCase(CaseModel):
    case_id: str
    image: str
    difficulty: Difficulty
    tags: list[str] = []
    derived_from: str | None = None
    """Set when the image is a generated variant of another case's image."""
    notes: str | None = None
    expectation: Expectation

    def image_path(self, root: Path) -> Path:
        return (root / self.image).resolve()


def load_case(path: Path) -> EvalCase:
    return EvalCase.model_validate_json(path.read_text(encoding="utf-8"))


def load_cases(cases_dir: Path) -> list[EvalCase]:
    cases = [load_case(path) for path in sorted(cases_dir.glob("*.json"))]
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise ValueError(f"duplicate case_id {case.case_id!r}")
        seen.add(case.case_id)
    return cases


def dump_case(case: EvalCase) -> str:
    return json.dumps(case.model_dump(mode="json", exclude_none=True), indent=2) + "\n"
