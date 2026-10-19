"""Standalone I-Spy game contracts."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.base import ApiModel
from app.schemas.media import MediaAsset


class StartISpyGameRequest(ApiModel):
    language_profile_id: UUID
    media_asset_id: UUID
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)]


class ISpyPhoto(ApiModel):
    media_asset: MediaAsset
    title: str
    playable: bool
    confirmed_at: AwareDatetime | None = None


class ISpyPhotoPage(ApiModel):
    photos: list[ISpyPhoto]
    next_cursor: str | None = None
