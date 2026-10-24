"""Stateless guest-demo contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.media import MAX_IMAGE_BYTES, AnchorPoint, BoundingBox


class DemoPhotoRequest(ApiModel):
    image_base64: Annotated[str, Field(min_length=4, max_length=(MAX_IMAGE_BYTES * 4 // 3) + 16)]
    target_language: Literal["es", "fr", "de", "ko"]


class DemoWord(ApiModel):
    id: UUID
    source: NonEmptyText
    translation: NonEmptyText
    article: str | None = None
    gender: str | None = None
    phonetic_text: str | None = None
    bounding_box: BoundingBox | None = None
    anchor_point: AnchorPoint | None = None


class DemoTerm(ApiModel):
    source: NonEmptyText
    translation: NonEmptyText


class DemoPhotoResponse(ApiModel):
    id: UUID
    title: NonEmptyText
    summary: str | None = None
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    words: Annotated[list[DemoWord], Field(min_length=5, max_length=5)]
    adjectives: Annotated[list[DemoTerm], Field(max_length=3)] = Field(default_factory=list)
    prepositions: Annotated[list[DemoTerm], Field(max_length=3)] = Field(default_factory=list)
