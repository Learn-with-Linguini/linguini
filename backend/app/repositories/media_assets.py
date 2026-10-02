"""Media metadata lookup shared by scene hydration and ownership-aware reads."""

from datetime import datetime
from typing import NamedTuple, Protocol
from uuid import UUID

from app.schemas.media import MediaAsset


class MediaAssetStorageError(Exception):
    pass


class MediaAssetConflictError(Exception):
    pass


class SessionImage(NamedTuple):
    session_id: UUID
    completed_at: datetime
    asset: MediaAsset


class MediaAssetRepository(Protocol):
    def create(self, asset: MediaAsset) -> MediaAsset: ...
    def get_by_ids(self, asset_ids: list[UUID]) -> dict[UUID, MediaAsset]: ...
    def list_completed_session_images(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[SessionImage]: ...
    def list_session_translation_suggestions(
        self, user_id: UUID, language_profile_id: UUID, start: datetime, end: datetime
    ) -> list[str]: ...
