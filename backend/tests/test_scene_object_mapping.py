"""Scene-object storage must retain all fields needed by session responses."""

from uuid import uuid4

from sqlalchemy import insert, select

from app.repositories.postgres.scene_objects import object_values, parse_object, scene_objects
from app.schemas.media import SceneObject


def test_anchor_point_is_selected_and_can_be_persisted():
    obj = SceneObject(
        session_id=uuid4(), label="table", anchor_point={"x": 0.2, "y": 0.7}
    )
    values = object_values(obj)
    statement = insert(scene_objects).values(**values).compile()
    assert statement.params["anchor_point"] == {"x": 0.2, "y": 0.7}
    selected = select(scene_objects).selected_columns
    assert set(SceneObject.model_fields) <= set(selected.keys())
    assert parse_object(values).anchor_point == obj.anchor_point


def test_legacy_object_without_anchor_point_still_loads():
    obj = parse_object({"id": uuid4(), "session_id": uuid4(), "label": "table"})
    assert obj.anchor_point is None
