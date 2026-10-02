"""Media upload and scene-understanding schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel, EntityModel, JsonObject, NonEmptyText, UnitScore
from app.schemas.enums import MediaSource, MediaType


class MediaAsset(EntityModel):
    owner_user_id: UUID | None = None
    media_type: MediaType
    source: MediaSource
    storage_key: NonEmptyText
    mime_type: NonEmptyText
    width: Annotated[int, Field(gt=0)] | None = None
    height: Annotated[int, Field(gt=0)] | None = None
    duration_ms: Annotated[int, Field(gt=0)] | None = None
    captured_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_media_metadata(self) -> MediaAsset:
        if (
            not self.mime_type.lower().startswith(f"{self.media_type.value}/")
            or not self.mime_type.split("/", 1)[-1]
        ):
            raise ValueError("mimeType must match mediaType and include a subtype")
        if (
            self.source in (MediaSource.USER_UPLOAD, MediaSource.CAMERA)
            and self.owner_user_id is None
        ):
            raise ValueError("uploaded and camera assets require ownerUserId")
        if self.media_type is MediaType.IMAGE and self.duration_ms is not None:
            raise ValueError("image assets cannot have durationMs")
        if self.media_type is MediaType.AUDIO and (
            self.width is not None or self.height is not None
        ):
            raise ValueError("audio assets cannot have image dimensions")
        if self.source is MediaSource.PRELOADED and self.owner_user_id is not None:
            raise ValueError("preloaded assets cannot have an ownerUserId")
        return self


class BoundingBox(ApiModel):
    """Normalized image coordinates in the inclusive range 0..1."""

    x: Annotated[Decimal, Field(ge=0, le=1)]
    y: Annotated[Decimal, Field(ge=0, le=1)]
    width: Annotated[Decimal, Field(gt=0, le=1)]
    height: Annotated[Decimal, Field(gt=0, le=1)]

    @model_validator(mode="after")
    def remain_inside_image(self) -> BoundingBox:
        if self.x + self.width > 1:
            raise ValueError("x + width must not exceed 1")
        if self.y + self.height > 1:
            raise ValueError("y + height must not exceed 1")
        return self


class AnchorPoint(ApiModel):
    """Normalized representative point used for the scene marker."""

    x: Annotated[Decimal, Field(ge=0, le=1)]
    y: Annotated[Decimal, Field(ge=0, le=1)]


class SceneObject(ApiModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    label: NonEmptyText
    bounding_box: BoundingBox | None = None
    anchor_point: AnchorPoint | None = None
    attributes: JsonObject | None = None
    confidence_score: UnitScore | None = None
    source_object_key: NonEmptyText | None = None
    vocabulary_item_id: UUID | None = None


class SceneObjectRelation(ApiModel):
    id: UUID = Field(default_factory=uuid4)
    subject_scene_object_id: UUID
    relation: Annotated[str, Field(min_length=1, max_length=200)]
    reference_scene_object_id: UUID
    source_relation_key: NonEmptyText | None = None

    @model_validator(mode="after")
    def distinct_objects(self):
        if self.subject_scene_object_id == self.reference_scene_object_id:
            raise ValueError("A relation must connect two different objects.")
        return self


MAX_IMAGE_BYTES = 10 * 1024 * 1024
ImageMime = Literal["image/jpeg", "image/png", "image/webp"]
UploadSource = Literal[MediaSource.CAMERA, MediaSource.USER_UPLOAD]


class CreateUploadUrlRequest(ApiModel):
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    file_size: Annotated[int, Field(strict=True, gt=0, le=MAX_IMAGE_BYTES)]
    mime_type: ImageMime
    source: UploadSource


class CreateUploadUrlResponse(ApiModel):
    asset_id: UUID
    upload_url: NonEmptyText
    storage_key: NonEmptyText
    expires_in_seconds: Annotated[int, Field(gt=0)]


class ConfirmMediaUploadRequest(ApiModel):
    asset_id: UUID
    storage_key: NonEmptyText
    source: UploadSource


class MediaAssetResponse(MediaAsset):
    signed_url: str
    expires_in_seconds: int = 3600


class PreloadedScene(ApiModel):
    image_url: str | None = None
    language_code: NonEmptyText = "es"
    scene_id: NonEmptyText
    language: NonEmptyText
    media_asset: MediaAsset
    title: NonEmptyText
    description: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
