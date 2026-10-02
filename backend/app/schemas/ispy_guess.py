"""Structured result for interpreting a learner's I-Spy description."""

from typing import Annotated

from pydantic import Field

from app.schemas.base import ApiModel, NonEmptyText


class ISpyGuessResult(ApiModel):
    guessed_object_key: NonEmptyText | None
    ambiguous: bool
    alternative_object_keys: list[NonEmptyText] = Field(default_factory=list)
    matched_evidence_keys: list[NonEmptyText] = Field(default_factory=list)
    contradicted_evidence_keys: list[NonEmptyText] = Field(default_factory=list)
    feedback: Annotated[str, Field(min_length=1, max_length=500)]
