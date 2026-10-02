"""SQLAlchemy metadata persistence; only trusted server code may register assets."""

from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import read_connection
from app.repositories.media_assets import (
    MediaAssetConflictError,
    MediaAssetStorageError,
    SessionImage,
)
from app.schemas.media import MediaAsset

media_assets = Table(
    "media_assets",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("owner_user_id", Uuid),
    Column("media_type", String(5), nullable=False),
    Column("source", String(10), nullable=False),
    Column("storage_key", Text, nullable=False),
    Column("mime_type", Text, nullable=False),
    Column("width", Integer),
    Column("height", Integer),
    Column("duration_ms", Integer),
    Column("captured_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


class PostgresMediaAssetRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_by_ids(self, asset_ids: list[UUID]) -> dict[UUID, MediaAsset]:
        if not asset_ids:
            return {}
        try:
            with read_connection(self.engine) as connection:
                rows = connection.execute(
                    select(media_assets).where(media_assets.c.id.in_(asset_ids))
                ).mappings()
                return {row["id"]: MediaAsset.model_validate(dict(row)) for row in rows}
        except (SQLAlchemyError, ValidationError) as exc:
            raise MediaAssetStorageError("Unable to read media assets.") from exc

    def list_completed_session_images(
        self, user_id: UUID, start: datetime, end: datetime
    ) -> list[SessionImage]:
        from app.repositories.postgres.practice import sessions

        try:
            with read_connection(self.engine) as connection:
                rows = connection.execute(
                    select(
                        sessions.c.id.label("session_id"),
                        sessions.c.completed_at,
                        media_assets,
                    )
                    .select_from(
                        sessions.join(
                            media_assets,
                            sessions.c.scene_media_asset_id == media_assets.c.id,
                        )
                    )
                    .where(
                        sessions.c.user_id == user_id,
                        sessions.c.status == "completed",
                        sessions.c.completed_at >= start,
                        sessions.c.completed_at < end,
                        media_assets.c.media_type == "image",
                    )
                    .order_by(sessions.c.completed_at.asc())
                ).mappings()
                seen: set[UUID] = set()
                images: list[SessionImage] = []
                asset_columns = {column.key for column in media_assets.c}
                for row in rows:
                    asset = MediaAsset.model_validate(
                        {key: value for key, value in dict(row).items() if key in asset_columns}
                    )
                    if asset.id in seen:
                        continue
                    seen.add(asset.id)
                    images.append(
                        SessionImage(
                            session_id=row["session_id"],
                            completed_at=row["completed_at"],
                            asset=asset,
                        )
                    )
                return images
        except (SQLAlchemyError, ValidationError) as exc:
            raise MediaAssetStorageError("Unable to read session images.") from exc

    def list_session_translation_suggestions(
        self, user_id: UUID, language_profile_id: UUID, start: datetime, end: datetime
    ) -> list[str]:
        """Return every translated object, attribute, and relation from a day's photos."""
        from app.repositories.postgres.practice import sessions

        try:
            with read_connection(self.engine) as connection:
                drafts = connection.execute(
                    select(sessions.c.analysis_draft).where(
                        sessions.c.user_id == user_id,
                        sessions.c.language_profile_id == language_profile_id,
                        sessions.c.started_at >= start,
                        sessions.c.started_at < end,
                    ).order_by(sessions.c.started_at.asc(), sessions.c.id.asc())
                ).scalars()
                suggestions: list[str] = []
                seen: set[str] = set()
                for draft in drafts:
                    preview = draft.get("translationPreview", {}) if isinstance(draft, dict) else {}
                    for category in ("objects", "attributes", "relationships"):
                        for term in preview.get(category, []):
                            word = term.get("translation") if isinstance(term, dict) else None
                            normalized = word.strip() if isinstance(word, str) else ""
                            key = normalized.casefold()
                            if normalized and key not in seen:
                                suggestions.append(normalized)
                                seen.add(key)
                return suggestions
        except SQLAlchemyError as exc:
            raise MediaAssetStorageError("Unable to read session suggestions.") from exc

    def create(self, asset: MediaAsset) -> MediaAsset:
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        insert(media_assets)
                        .values(**asset.model_dump(by_alias=False))
                        .returning(media_assets)
                    )
                    .mappings()
                    .one()
                )
                return MediaAsset.model_validate(dict(row))
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise MediaAssetConflictError("Media asset or storage key already exists.") from exc
            raise MediaAssetStorageError("Unable to save media asset.") from exc
        except (SQLAlchemyError, ValidationError) as exc:
            raise MediaAssetStorageError("Unable to save media asset.") from exc
