"""Structured output contracts for target-blind I-Spy description evaluation.

Owns the static result model plus the dynamic response-model factory that
restricts object and evidence keys to the supplied scene at schema level.
The length/count bounds bind when the response is parsed locally —
``build_strict_json_schema`` strips those keywords from the provider schema.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, create_model

from app.schemas.base import ApiModel, NonEmptyText

MAX_ALTERNATIVE_KEYS = 4
MAX_EVIDENCE_KEYS = 12
MAX_FEEDBACK_LENGTH = 500

_Key = Annotated[NonEmptyText, Field(max_length=200)]


class ISpyGuessResult(ApiModel):
    guessed_object_key: _Key | None
    ambiguous: bool
    alternative_object_keys: Annotated[
        list[_Key], Field(max_length=MAX_ALTERNATIVE_KEYS)
    ] = Field(default_factory=list)
    matched_evidence_keys: Annotated[
        list[_Key], Field(max_length=MAX_EVIDENCE_KEYS)
    ] = Field(default_factory=list)
    contradicted_evidence_keys: Annotated[
        list[_Key], Field(max_length=MAX_EVIDENCE_KEYS)
    ] = Field(default_factory=list)
    feedback: Annotated[str, Field(min_length=1, max_length=MAX_FEEDBACK_LENGTH)]


@lru_cache(maxsize=32)
def _response_model(
    object_keys: tuple[str, ...], evidence_keys: tuple[str, ...]
) -> type[ApiModel]:
    key_type = Literal.__getitem__(object_keys)
    evidence_type = Literal.__getitem__(evidence_keys) if evidence_keys else str
    evidence_bound = MAX_EVIDENCE_KEYS if evidence_keys else 0
    return create_model(
        "GroundedISpyGuessResult",
        __base__=ISpyGuessResult,
        guessed_object_key=(key_type | None, ...),
        alternative_object_keys=(
            list[key_type], Field(max_length=MAX_ALTERNATIVE_KEYS)
        ),
        matched_evidence_keys=(list[evidence_type], Field(max_length=evidence_bound)),
        contradicted_evidence_keys=(
            list[evidence_type], Field(max_length=evidence_bound)
        ),
    )


def scene_guess_response_model(payload: dict) -> type[ApiModel]:
    # Local import: schemas must not pull validation (which needs this module).
    from app.ai.features.ispy_guess.validation import ISpyGuessError

    scene = payload.get("sceneObjects", {})
    object_keys = tuple(dict.fromkeys(row["key"] for row in scene.get("objects", [])))
    if not object_keys:
        raise ISpyGuessError("I-Spy guessing needs at least one scene object.")
    evidence_keys = tuple(
        dict.fromkeys(
            row["key"]
            for field in ("attributes", "relations")
            for row in scene.get(field, [])
        )
    )
    return _response_model(object_keys, evidence_keys)
