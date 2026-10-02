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
from app.repositories.scenes import SceneStorageError
from app.schemas.scenes import PreloadedSceneDetail
from app.services.scenes import SceneService


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
            .values(is_active=True, language_code="fr")
        )
    assert client.get(f"/api/v1/preloaded-scenes/{slug}").status_code == 404
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
    row["languageCode"] = "not a language"
    with pytest.raises(IntegrityError), engine.begin() as connection:
        store_scene(connection, PreloadedSceneDetail.model_validate(row))
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(media_assets.c.id).where(media_assets.c.id == UUID(row["mediaAsset"]["id"]))
            ).first()
            is None
        )


def test_french_scene_round_trip(database, source):
    engine, *_ = database
    source["languageCode"] = "fr"
    source["language"] = "French"
    source["items"][0]["gender"] = "le"
    source["items"][1]["gender"] = "l'"
    scene = PreloadedSceneDetail.model_validate(source)
    with engine.begin() as connection:
        store_scene(connection, scene)
    try:
        service = SceneService(PostgresSceneRepository(engine))
        french = service.list_scenes("fr")
        assert source["sceneId"] in {row.scene_id for row in french}
        assert service.list_scenes("es")
        fetched = service.get_scene(source["sceneId"], "fr")
        assert [item.gender for item in fetched.items][:2] == ["le", "l'"]
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


def test_precompute_helpers_build_valid_content():
    from app.ai.features.translation.schemas import TranslatedTerm
    from app.schemas.media import AnchorPoint, BoundingBox, MediaAsset, SceneObject
    from app.scripts.precompute_preloaded_scenes import (
        build_items,
        build_scene_content,
        dedupe_objects,
        marker_percent,
        normalized_gender,
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
    ]
    kept = dedupe_objects(objects)
    assert [obj.label for obj in kept] == ["Street", "school"]
    assert marker_percent(kept[0]) == (30.0, 30.0)
    assert marker_percent(kept[1]) == (50.0, 50.0)

    terms = [
        TranslatedTerm(
            key=str(kept[0].id), source="Street", translation="rue",
            article="la", gender="feminine",
        ),
        TranslatedTerm(
            key=str(kept[1].id), source="school", translation="école",
            article="l'", gender="feminine",
        ),
    ]
    examples = {str(kept[0].id): ("La rue est calme.", "The street is quiet.")}
    items = build_items(kept, terms, examples, "fr")
    assert items[0]["id"] == "street"
    assert items[0]["word"] == "la rue"
    assert items[0]["translation"] == "the Street"
    assert items[0]["gender"] == "la"
    assert items[1]["id"] == "school"
    assert items[1]["word"] == "l'école"
    assert items[1]["gender"] == "l'"
    assert items[1]["example"] == ""

    assert normalized_gender("du", "masculine", "fr") == "le"
    assert normalized_gender("du", "feminine", "es") == "la"
    assert normalized_gender(None, None, "es") is None

    asset = MediaAsset(
        media_type="image", source="preloaded",
        storage_key="preloaded/scenes/street.jpg", mime_type="image/jpeg",
        width=320, height=200,
    )
    content = build_scene_content(
        slug="rue-principale", language_code="fr", language="French",
        title="A walk downtown", description="A busy street.",
        difficulty="beginner", media_asset=asset, items=items,
    )
    detail = PreloadedSceneDetail.model_validate(
        {
            **content,
            "sceneId": "rue-principale",
            "languageCode": "fr",
            "language": "French",
            "title": "A walk downtown",
            "description": "A busy street.",
            "difficulty": "beginner",
            "mediaAsset": asset,
        }
    )
    assert len(detail.items) == 2
    assert detail.tasks[0].item_ids == [item["id"] for item in items]


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
