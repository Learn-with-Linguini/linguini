"""Database scene templates, preserving the frontend's slug-based scene contract."""

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from app.database import read_connection
from app.repositories.postgres.media_assets import media_assets
from app.repositories.scenes import SceneStorageError
from app.schemas.media import MediaAsset
from app.schemas.scenes import PreloadedSceneDetail

CONTENT_FIELDS = {"items", "tasks", "rounds", "prompts", "relations"}
preloaded_scenes = Table(
    "preloaded_scenes",
    MetaData(),
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("slug", Text, nullable=False),
    Column("language_code", String(35), nullable=False),
    Column("language", Text, nullable=False),
    Column("media_asset_id", Uuid, nullable=False),
    Column("title", Text, nullable=False),
    Column("description", Text),
    Column("difficulty", String(12), nullable=False),
    Column("content", JSONB, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


class PostgresSceneRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_scenes(self) -> list[PreloadedSceneDetail]:
        try:
            with read_connection(self.engine) as connection:
                rows = connection.execute(
                    select(
                        preloaded_scenes,
                        *[column.label(f"asset_{column.name}") for column in media_assets.c],
                    )
                    .select_from(
                        preloaded_scenes.join(
                            media_assets, media_assets.c.id == preloaded_scenes.c.media_asset_id
                        )
                    )
                    .where(preloaded_scenes.c.is_active.is_(True))
                    .order_by(preloaded_scenes.c.sort_order, preloaded_scenes.c.slug)
                ).mappings()
                result = []
                for row in rows:
                    content = {
                        key: row["content"].get(key, []) if key == "relations"
                        else row["content"][key]
                        for key in CONTENT_FIELDS
                    }
                    asset = MediaAsset.model_validate(
                        {column.name: row[f"asset_{column.name}"] for column in media_assets.c}
                    )
                    result.append(
                        PreloadedSceneDetail.model_validate(
                            {
                                **content,
                                **{
                                    key: row[key]
                                    for key in (
                                        "language_code",
                                        "language",
                                        "title",
                                        "description",
                                        "difficulty",
                                    )
                                },
                                "scene_id": row["slug"],
                                "media_asset": asset,
                            }
                        )
                    )
                return result
        except (SQLAlchemyError, ValidationError, KeyError, TypeError) as exc:
            raise SceneStorageError("Unable to load scenes.") from exc
