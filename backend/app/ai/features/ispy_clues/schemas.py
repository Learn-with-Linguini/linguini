"""Structured output contracts for generated I-Spy clues.

Owns the static result models plus the dynamic response-model factory that
restricts answer and reference keys to the supplied scene at schema level.
The added length/count bounds below bind when the response is parsed locally —
``build_strict_json_schema`` strips those keywords from the provider schema.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, create_model

from app.schemas.base import ApiModel, NonEmptyText


class GeneratedISpyClue(ApiModel):
    """One clue ending and its private scene-object answer."""

    clue: NonEmptyText = Field(
        max_length=200,
        description="Only the phrase completing 'I spy with my little eye, something that …'."
    )
    clue_translation: Annotated[str, Field(max_length=200)] = Field(
        default="",
        description="English translation of `clue`, without the I-Spy opening.",
    )
    answer_object_key: NonEmptyText = Field(max_length=200)
    object_keys: Annotated[
        list[Annotated[NonEmptyText, Field(max_length=200)]],
        Field(min_length=1, max_length=1),
    ]
    relationship_keys: Annotated[
        list[Annotated[NonEmptyText, Field(max_length=200)]],
        Field(max_length=4),
    ] = Field(default_factory=list)


class ISpyClueResult(ApiModel):
    clues: Annotated[list[GeneratedISpyClue], Field(min_length=1, max_length=2)]


@lru_cache(maxsize=32)
def _response_model(
    object_keys: tuple[str, ...], relationship_keys: tuple[str, ...]
) -> type[ApiModel]:
    clue = create_model(
        "GroundedISpyClue",
        __base__=GeneratedISpyClue,
        answer_object_key=(Literal.__getitem__(object_keys), ...),
        object_keys=(
            list[Literal.__getitem__(object_keys)], Field(min_length=1, max_length=1)
        ),
        relationship_keys=(
            list[Literal.__getitem__(relationship_keys)] if relationship_keys else list[str],
            Field(max_length=4) if relationship_keys else Field(max_length=0),
        ),
    )
    return create_model(
        "GroundedISpyClueResult",
        __base__=ISpyClueResult,
        clues=(list[clue], Field(min_length=1, max_length=2)),
    )


def scene_clue_response_model(payload: dict) -> type[ApiModel]:
    # Local import: schemas must not pull validation (which needs this module).
    from app.ai.features.ispy_clues.validation import ISpyClueGenerationError

    object_keys = tuple(dict.fromkeys(row["key"] for row in payload.get("objects", [])))
    if not object_keys:
        raise ISpyClueGenerationError("I-Spy clues need at least one scene object.")
    relationship_keys = tuple(
        dict.fromkeys(row["key"] for row in payload.get("relationships", []))
    )
    return _response_model(object_keys, relationship_keys)
