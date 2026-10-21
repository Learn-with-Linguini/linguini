from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import (
    Column,
    Engine,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from app.database import read_connection
from app.repositories.postgres.practice import sessions
from app.repositories.practice import PracticeStorageError
from app.schemas.media import SceneObject

scene_objects = Table(
    "scene_objects",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("session_id", Uuid, nullable=False),
    Column("label", Text, nullable=False),
    Column("bounding_box", JSONB(none_as_null=True)),
    Column("anchor_point", JSONB(none_as_null=True)),
    Column("attributes", JSONB(none_as_null=True)),
    Column("confidence_score", Numeric(6, 5)),
    Column("source_object_key", Text),
    Column("vocabulary_item_id", Uuid),
    schema="public",
)


scene_object_relations = Table(
    "scene_object_relations",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("subject_scene_object_id", Uuid, nullable=False),
    Column("relation", Text, nullable=False),
    Column("reference_scene_object_id", Uuid, nullable=False),
    Column("source_relation_key", Text),
    schema="public",
)


def object_values(item: SceneObject) -> dict:
    values = item.model_dump(by_alias=False)
    if item.bounding_box:
        values["bounding_box"] = {
            key: float(value) for key, value in item.bounding_box.model_dump().items()
        }
    if item.anchor_point:
        values["anchor_point"] = {
            key: float(value) for key, value in item.anchor_point.model_dump().items()
        }
    return values


def parse_object(row) -> SceneObject:
    return SceneObject.model_validate(dict(row))


class PostgresSceneObjectRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_for_session(self, session_id: UUID, user_id: UUID) -> list[SceneObject]:
        try:
            with read_connection(self.engine) as connection:
                return [
                    parse_object(row)
                    for row in connection.execute(
                        select(scene_objects)
                        .join(sessions, sessions.c.id == scene_objects.c.session_id)
                        .where(sessions.c.id == session_id, sessions.c.user_id == user_id)
                        .order_by(scene_objects.c.id)
                    ).mappings()
                ]
        except (SQLAlchemyError, ValidationError) as exc:
            raise PracticeStorageError("Unable to load scene objects.") from exc

    def create(self, item: SceneObject) -> SceneObject:
        """Trusted detector/import metadata, never arbitrary frontend detections."""
        try:
            with self.engine.begin() as connection:
                return parse_object(
                    connection.execute(
                        insert(scene_objects).values(**object_values(item)).returning(scene_objects)
                    )
                    .mappings()
                    .one()
                )
        except (SQLAlchemyError, ValidationError) as exc:
            raise PracticeStorageError("Unable to save scene object.") from exc
