from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from test_postgres_sessions import database as database

from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.scenes import (
    PostgresSceneRepository,
    preloaded_scenes,
)
from app.repositories.postgres.vocabulary import vocabulary_items, vocabulary_translations
from app.repositories.scenes import SceneStorageError
from app.schemas.scenes import PreloadedSceneDetail
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation
from app.services.scenes import SceneService
from app.services.session_plan import curated_word


def store_scene(connection, scene):
    connection.execute(insert(media_assets).values(**scene.media_asset.model_dump(by_alias=False)))
    values = scene.model_dump(
        by_alias=False,
        exclude={
            "items",
            "tasks",
            "rounds",
            "prompts",
            "relations",
            "media_asset",
            "scene_id",
            "image_url",
        },
    )
    connection.execute(
        insert(preloaded_scenes).values(
            **values,
            slug=scene.scene_id,
            media_asset_id=scene.media_asset.id,
            content=scene.model_dump(
                mode="json",
                by_alias=True,
                include={"items", "tasks", "rounds", "prompts", "relations"},
            ),
        )
    )


@pytest.mark.parametrize("string_mode", ["on", "off"])
def test_exported_migration_preserves_quoted_and_backslashed_scene_text(scene_record, string_mode):
    from app.scripts.precompute_preloaded_scenes import emit_migration_sql

    engine, _client, source = scene_record
    with engine.connect() as connection:
        row = dict(connection.execute(
            select(preloaded_scenes).where(preloaded_scenes.c.slug == source["sceneId"])
        ).mappings().one())
    row.update(
        title="O'Brien\\'; SELECT 123; --",
        description="A path C:\\photos\\ with 'quoted' text",
        content={**row["content"], "exportTest": "\\'; SELECT 456; --"},
    )
    with engine.connect().execution_options(
        isolation_level="AUTOCOMMIT", no_parameters=True,
    ) as connection:
        # The generated file must not depend on the caller's string mode.
        connection.exec_driver_sql(
            "SET standard_conforming_strings = on"
            if string_mode == "on"
            else "SET standard_conforming_strings = off"
        )
        try:
            connection.exec_driver_sql(emit_migration_sql([row]))
            saved = connection.execute(
                select(preloaded_scenes).where(preloaded_scenes.c.id == row["id"])
            ).mappings().one()
            assert saved["title"] == row["title"]
            assert saved["description"] == row["description"]
            assert saved["content"]["exportTest"] == row["content"]["exportTest"]
        finally:
            connection.exec_driver_sql("ROLLBACK")
            connection.exec_driver_sql("RESET standard_conforming_strings")


@pytest.fixture
def source(database):
    engine, *_ = database
    row = PostgresSceneRepository(engine).list_scenes()[0].model_dump(mode="json", by_alias=True)
    row["sceneId"] = f"test-{uuid4()}"
    row["mediaAsset"]["id"] = str(uuid4())
    row["mediaAsset"]["storageKey"] = f"test/{uuid4()}"
    return row


@pytest.fixture
def scene_record(database, source):
    engine, _, _, client = database
    row = source
    with engine.begin() as connection:
        store_scene(connection, PreloadedSceneDetail.model_validate(row))
    yield engine, client, row
    with engine.begin() as connection:
        connection.execute(
            delete(preloaded_scenes).where(preloaded_scenes.c.slug == row["sceneId"])
        )
        connection.execute(
            delete(media_assets).where(media_assets.c.id == UUID(row["mediaAsset"]["id"]))
        )


def test_api_and_visibility(scene_record):
    engine, client, row = scene_record
    slug = row["sceneId"]
    response = client.get(f"/api/v1/preloaded-scenes/{slug}")
    assert response.status_code == 200
    expected = PreloadedSceneDetail.model_validate(row).model_dump(mode="json", by_alias=True)
    assert {"tasks", "rounds", "prompts", "art"}.isdisjoint(response.json())
    for key in ("sceneId", "items", "title"):
        assert response.json()[key] == expected[key]
    with engine.begin() as connection:
        connection.execute(
            update(preloaded_scenes)
            .where(preloaded_scenes.c.slug == slug)
            .values(title="Live edit", sort_order=0, is_active=False)
        )
    assert client.get(f"/api/v1/preloaded-scenes/{slug}").status_code == 404
    with engine.begin() as connection:
        connection.execute(
            update(preloaded_scenes)
            .where(preloaded_scenes.c.slug == slug)
            .values(is_active=True)
        )
    assert client.get(f"/api/v1/preloaded-scenes/{slug}").status_code == 200
    assert (
        next(r for r in PostgresSceneRepository(engine).list_scenes() if r.scene_id == slug).title
        == "Live edit"
    )


def test_media_integrity_and_rls(scene_record):
    engine, _, row = scene_record
    asset_id = UUID(row["mediaAsset"]["id"])
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(delete(media_assets).where(media_assets.c.id == asset_id))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(media_assets).where(media_assets.c.id == asset_id).values(source="generated")
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(preloaded_scenes)
            .where(preloaded_scenes.c.slug == row["sceneId"])
            .values(media_asset_id=uuid4())
        )
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT relrowsecurity FROM pg_class WHERE oid='public.preloaded_scenes'::regclass"
            )
        ).scalar_one()


def test_transaction_rolls_back_media_on_invalid_scene(database, source):
    engine, *_ = database
    row = source
    row["sceneId"] = PostgresSceneRepository(engine).list_scenes()[0].scene_id
    with pytest.raises(IntegrityError), engine.begin() as connection:
        store_scene(connection, PreloadedSceneDetail.model_validate(row))
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(media_assets.c.id).where(media_assets.c.id == UUID(row["mediaAsset"]["id"]))
            ).first()
            is None
        )


def test_scenes_are_language_independent(database, source):
    engine, *_ = database
    scene = PreloadedSceneDetail.model_validate(source)
    with engine.begin() as connection:
        store_scene(connection, scene)
    try:
        service = SceneService(PostgresSceneRepository(engine))
        listed = service.list_scenes()
        assert source["sceneId"] in {row.scene_id for row in listed}
        assert all("language" not in row.model_dump() for row in listed)
        fetched = service.get_scene(source["sceneId"])
        assert [item.translation for item in fetched.items] == [
            item["translation"] for item in source["items"]
        ]
        assert all({"word", "gender", "example"}.isdisjoint(item) for item in source["items"])
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(preloaded_scenes).where(
                    preloaded_scenes.c.slug == source["sceneId"]
                )
            )
            connection.execute(
                delete(media_assets).where(
                    media_assets.c.id == UUID(source["mediaAsset"]["id"])
                )
            )


def test_database_errors_are_controlled():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("select", {}, Exception("private"))
    with pytest.raises(SceneStorageError, match="Unable to load scenes"):
        PostgresSceneRepository(engine).list_scenes()


def _scene_objects(labels, attributes=None):
    from app.schemas.media import SceneObject

    session_id = uuid4()
    attributes = attributes or {}
    return [
        SceneObject(
            session_id=session_id,
            label=label,
            attributes=attributes.get(index),
        )
        for index, label in enumerate(labels)
    ]


def test_select_objects_keeps_repeated_labels_and_normalizes_quantities():
    from app.scripts.precompute_preloaded_scenes import select_objects

    objects = _scene_objects(
        ["chair", "chair", "chair", "table"],
        {1: {"color": "brown"}, 3: {"quantity": "4"}},
    )

    kept = select_objects(objects)

    assert [obj.label for obj in kept] == ["chair", "chair", "chair", "table"]
    assert [obj.attributes["quantity"] for obj in kept[:3]] == ["3", "3", "3"]
    assert "quantity" not in (kept[3].attributes or {})


def test_select_objects_caps_distinct_labels():
    from app.scripts.precompute_preloaded_scenes import select_objects

    objects = _scene_objects([f"label-{index}" for index in range(8)])

    kept = select_objects(objects)

    assert [obj.label for obj in kept] == [f"label-{index}" for index in range(6)]


def test_select_objects_caps_instances_per_label():
    from app.scripts.precompute_preloaded_scenes import select_objects

    kept = select_objects(_scene_objects(["chair"] * 15))

    assert len(kept) == 10
    assert all(obj.attributes == {"quantity": "10"} for obj in kept)


def test_select_objects_caps_total_after_selecting_labels_breadth_first():
    from app.scripts.precompute_preloaded_scenes import select_objects

    labels = ["chair"] * 10 + ["table", "cup", "plate", "book", "lamp"]

    kept = select_objects(_scene_objects(labels))

    assert len(kept) == 12
    assert {obj.label for obj in kept} == {
        "chair", "table", "cup", "plate", "book", "lamp",
    }
    assert sum(obj.label == "chair" for obj in kept) == 7


def test_select_objects_does_not_mutate_input_objects():
    from app.scripts.precompute_preloaded_scenes import select_objects

    objects = _scene_objects(
        ["chair", "chair", "table"],
        {0: {"color": "brown"}, 1: {"quantity": "11"}, 2: {"quantity": "4"}},
    )
    original_attributes = [obj.attributes.copy() for obj in objects]

    kept = select_objects(objects)

    assert [obj.attributes for obj in objects] == original_attributes
    assert all(original is not selected for original, selected in zip(objects, kept, strict=True))
    assert kept[0].attributes == {"color": "brown", "quantity": "2"}
    assert kept[1].attributes == {"quantity": "2"}
    assert kept[2].attributes == {}


def test_precompute_helpers_build_valid_content():
    from app.schemas.media import AnchorPoint, BoundingBox, MediaAsset, SceneObject
    from app.scripts.precompute_preloaded_scenes import (
        box_centre_percent,
        build_items,
        build_scene_content,
        marker_percent,
        select_objects,
    )

    session_id = uuid4()
    objects = [
        SceneObject(
            session_id=session_id,
            label="Street",
            bounding_box=BoundingBox(x="0.1", y="0.2", width="0.4", height="0.2"),
        ),
        SceneObject(
            session_id=session_id,
            label="school",
            anchor_point=AnchorPoint(x="0.5", y="0.5"),
        ),
        SceneObject(session_id=session_id, label="STREET"),
        SceneObject(session_id=session_id, label="the pillow"),
    ]
    kept = select_objects(objects)
    assert [obj.label for obj in kept] == [
        "Street", "school", "STREET", "the pillow"
    ]
    assert [obj.attributes["quantity"] for obj in (kept[0], kept[2])] == ["2", "2"]
    assert box_centre_percent(-0.1, 0.12345, 0.3, 0.2) == (5.0, 22.3)
    assert box_centre_percent(1.1, 1.1, 0.2, 0.2) == (100.0, 100.0)
    assert marker_percent(kept[0]) == (30.0, 30.0)
    assert marker_percent(kept[1]) == (50.0, 50.0)

    items = build_items(kept)
    assert [item["id"] for item in items] == ["street", "school", "street-2", "pillow"]
    assert [item["translation"] for item in items] == [
        "Street", "school", "STREET", "pillow",
    ]
    assert [item["attributes"].get("quantity") for item in items] == [
        "2", None, "2", None
    ]
    assert all({"word", "gender", "example"}.isdisjoint(item) for item in items)

    asset = MediaAsset(
        media_type="image", source="preloaded",
        storage_key="preloaded/scenes/street.jpg", mime_type="image/jpeg",
        width=320, height=200,
    )
    content = build_scene_content(
        slug="street", title="A walk downtown", description="A busy street.",
        difficulty="beginner", media_asset=asset, items=items,
    )
    assert content["rounds"][0]["clue"] == "Street"
    detail = PreloadedSceneDetail.model_validate(
        {
            **content,
            "sceneId": "street",
            "title": "A walk downtown",
            "description": "A busy street.",
            "difficulty": "beginner",
            "mediaAsset": asset,
        }
    )
    assert len(detail.items) == 4
    assert detail.tasks[0].item_ids == [item["id"] for item in items]


def test_assign_instances_matches_nearest_same_label_and_keeps_unmatched():
    from app.ai.features.object_grounding import GroundedBox
    from app.scripts.precompute_preloaded_scenes import assign_instances

    items = [
        {"id": "pillow-1", "translation": "pillow", "x": 10, "y": 50},
        {"id": "pillow-2", "translation": "pillow", "x": 50, "y": 50},
        {"id": "pillow-3", "translation": "pillow", "x": 90, "y": 50},
    ]
    detections = {
        "the pillow": [
            GroundedBox(x=0.07, y=0.45, width=0.1, height=0.1, score=0.9),
            GroundedBox(x=0.5, y=0.45, width=0.1, height=0.1, score=0.8),
        ]
    }

    updated, ungrounded = assign_instances(items, detections)

    assert [(item["x"], item["y"]) for item in updated] == [
        (12.0, 50.0), (55.0, 50.0), (90, 50)
    ]
    assert ungrounded == ["pillow-3"]
    assert items[0]["x"] == 10


def test_assign_instances_never_crosses_labels_and_breaks_ties_deterministically():
    from app.ai.features.object_grounding import GroundedBox
    from app.scripts.precompute_preloaded_scenes import assign_instances

    items = [
        {"id": "first", "translation": "pillow", "x": 50, "y": 50},
        {"id": "second", "translation": "pillow", "x": 50, "y": 50},
        {"id": "bed", "translation": "bed", "x": 10, "y": 10},
    ]
    detections = {
        "pillow": [
            GroundedBox(x=0.35, y=0.45, width=0.1, height=0.1, score=0.8),
            GroundedBox(x=0.55, y=0.45, width=0.1, height=0.1, score=0.7),
        ],
        "bed": [
            GroundedBox(x=0.8, y=0.8, width=0.1, height=0.1, score=0.9)
        ],
    }

    updated, ungrounded = assign_instances(items, detections)

    assert [(item["x"], item["y"]) for item in updated] == [
        (40.0, 50.0), (60.0, 50.0), (85.0, 85.0)
    ]
    assert ungrounded == []


def test_reground_row_strips_legacy_articles_and_preserves_scene_facts():
    from app.ai.contracts import VisionImage
    from app.ai.features.object_grounding import GroundedBox
    from app.schemas.media import MediaAsset
    from app.scripts.precompute_preloaded_scenes import (
        build_scene_content,
        reground_row,
    )

    asset = MediaAsset(
        media_type="image",
        source="preloaded",
        storage_key="preloaded/bedroom.jpg",
        mime_type="image/jpeg",
        width=640,
        height=480,
    )
    items = [
        {
            "id": "the-pillow",
            "translation": "the pillow",
            "wordClass": "noun",
            "marker": 1,
            "x": 10,
            "y": 20,
            "attributes": {"color": "blue"},
        },
        {
            "id": "the-bed",
            "translation": "the bed",
            "wordClass": "noun",
            "marker": 2,
            "x": 70,
            "y": 80,
            "attributes": {},
        },
    ]
    content = build_scene_content(
        slug="bedroom",
        title="Bedroom",
        description="A blue pillow is on a bed.",
        difficulty="beginner",
        media_asset=asset,
        items=items,
        relations=[
            {
                "subjectItemId": "the-pillow",
                "relation": "on",
                "referenceItemId": "the-bed",
            }
        ],
    )
    content["generated"] = {"templates": [{"fingerprint": "stored"}]}
    row = {
        "slug": "bedroom",
        "title": "Bedroom",
        "description": "A blue pillow is on a bed.",
        "difficulty": "beginner",
        "content": content,
        "media_asset": asset,
    }

    class FakeGrounder:
        def __init__(self):
            self.calls = []

        def ground_instances(self, _image, labels, *, threshold=None):
            self.calls.append((labels, threshold))
            return {
                "pillow": [
                    GroundedBox(x=0.4, y=0.3, width=0.2, height=0.2, score=0.9)
                ],
                "bed": [
                    GroundedBox(x=0.1, y=0.2, width=0.2, height=0.2, score=0.8)
                ],
            }

    grounder = FakeGrounder()
    updated, ungrounded = reground_row(
        row, VisionImage(data=b"image", mime_type="image/jpeg"), grounder
    )

    assert grounder.calls == [(["pillow"], None), (["bed"], None)]
    assert [item["translation"] for item in updated["content"]["items"]] == [
        "pillow", "bed"
    ]
    assert [(item["x"], item["y"]) for item in updated["content"]["items"]] == [
        (50.0, 40.0), (20.0, 30.0)
    ]
    assert updated["content"]["items"][0]["attributes"] == {"color": "blue"}
    assert updated["content"]["relations"] == content["relations"]
    assert updated["content"]["generated"] == content["generated"]
    assert updated["content"]["rounds"][0]["clue"] == "pillow"
    assert ungrounded == []
    PreloadedSceneDetail.model_validate(
        {
            **{
                key: value
                for key, value in updated["content"].items()
                if key != "generated"
            },
            "sceneId": row["slug"],
            "title": row["title"],
            "description": row["description"],
            "difficulty": row["difficulty"],
            "mediaAsset": asset,
        }
    )


def test_reground_fallback_fills_only_unmatched_items_and_excludes_primary_box():
    from app.ai.contracts import VisionImage
    from app.ai.features.object_grounding import GroundedBox
    from app.schemas.media import MediaAsset
    from app.scripts.precompute_preloaded_scenes import (
        build_scene_content,
        reground_row,
    )

    asset = MediaAsset(
        media_type="image",
        source="preloaded",
        storage_key="preloaded/park.jpg",
        mime_type="image/jpeg",
        width=640,
        height=480,
    )
    items = [
        {
            "id": "pillow-1",
            "translation": "pillow",
            "wordClass": "noun",
            "marker": 1,
            "x": 50,
            "y": 50,
            "attributes": {},
        },
        {
            "id": "pillow-2",
            "translation": "pillow",
            "wordClass": "noun",
            "marker": 2,
            "x": 52,
            "y": 50,
            "attributes": {},
        },
        {
            "id": "bed",
            "translation": "bed",
            "wordClass": "noun",
            "marker": 3,
            "x": 20,
            "y": 20,
            "attributes": {},
        },
    ]
    content = build_scene_content(
        slug="park",
        title="Park",
        description="A pillow and a bed.",
        difficulty="beginner",
        media_asset=asset,
        items=items,
    )
    row = {
        "slug": "park",
        "title": "Park",
        "description": "A pillow and a bed.",
        "difficulty": "beginner",
        "content": content,
        "media_asset": asset,
    }

    class FakeGrounder:
        def __init__(self):
            self.calls = []

        def ground_instances(self, _image, labels, *, threshold=None):
            self.calls.append((labels, threshold))
            if threshold is not None:
                return {
                    "pillow": [
                        GroundedBox(
                            x=0.46, y=0.45, width=0.1, height=0.1, score=0.4
                        ),
                        GroundedBox(
                            x=0.85, y=0.45, width=0.1, height=0.1, score=0.3
                        ),
                    ]
                }
            if labels == ["pillow"]:
                return {
                    "pillow": [
                        GroundedBox(
                            x=0.46, y=0.45, width=0.1, height=0.1, score=0.9
                        )
                    ]
                }
            return {
                "bed": [
                    GroundedBox(
                        x=0.15, y=0.15, width=0.1, height=0.1, score=0.9
                    )
                ]
            }

    grounder = FakeGrounder()
    updated, ungrounded = reground_row(
        row,
        VisionImage(data=b"image", mime_type="image/jpeg"),
        grounder,
        fallback_threshold=0.25,
    )

    assert grounder.calls == [
        (["pillow"], None),
        (["bed"], None),
        (["pillow"], 0.25),
    ]
    assert [(item["x"], item["y"]) for item in updated["content"]["items"]] == [
        (51.0, 50.0),
        (90.0, 50.0),
        (20.0, 20.0),
    ]
    assert ungrounded == []


@pytest.mark.parametrize("invalid", ["duplicate", "reference", "coordinates"])
def test_scene_content_validation(source, invalid):
    if invalid == "duplicate":
        source["items"].append(source["items"][0])
    elif invalid == "reference":
        source["tasks"][0]["itemIds"] = ["unknown"]
    else:
        source["items"][0]["x"] = 101
    with pytest.raises(ValueError):
        PreloadedSceneDetail.model_validate(source)


def test_curated_word_matches_bare_and_article_prefixed_catalog_translations(database):
    engine, _owner, profile, _client = database
    old = datetime(2000, 1, 1, tzinfo=UTC)
    entries = []
    for translation in ("the bench", "chair"):
        item = VocabularyItem(
            language_code=profile.target_language_code,
            lemma=f"test-{translation.replace(' ', '-')}-{uuid4()}",
            display_text=f"test-{translation}",
            part_of_speech="noun",
        ).model_copy(update={"created_at": old, "updated_at": old})
        translated = VocabularyTranslation(
            vocabulary_item_id=item.id,
            source_language_code=profile.source_language_code,
            translated_text=translation,
        ).model_copy(update={"created_at": old, "updated_at": old})
        entries.append((item, translated))
    with engine.begin() as connection:
        for item, translation in entries:
            connection.execute(
                insert(vocabulary_items).values(**item.model_dump(by_alias=False))
            )
            connection.execute(
                insert(vocabulary_translations).values(
                    **translation.model_dump(by_alias=False)
                )
            )
    try:
        with engine.connect() as connection:
            bench = curated_word(
                connection, profile.model_dump(by_alias=False), "bench"
            )
            chair = curated_word(
                connection, profile.model_dump(by_alias=False), "the chair"
            )
        assert bench is not None and bench[0].id == entries[0][0].id
        assert bench[1].translated_text == "the bench"
        assert chair is not None and chair[0].id == entries[1][0].id
        assert chair[1].translated_text == "chair"
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(vocabulary_translations).where(
                    vocabulary_translations.c.vocabulary_item_id.in_(
                        [item.id for item, _translation in entries]
                    )
                )
            )
            connection.execute(
                delete(vocabulary_items).where(
                    vocabulary_items.c.id.in_([item.id for item, _ in entries])
                )
            )
