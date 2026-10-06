"""Learner sessions reuse precomputed templates only for unchanged curated scenes."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select
from test_postgres_sessions import database as database
from test_preloaded_templates import (
    RESERVE,
    SceneModel,
    scene_row,
    services,
    unlimited,
)

from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scenes import PostgresSceneRepository, preloaded_scenes
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.sessions import ReviewPracticeRequest
from app.scripts.preloaded_templates import generate_row_templates


@pytest.fixture
def curated(database):
    engine, owner, profile, client = database
    asset = PostgresSceneRepository(engine).list_scenes()[0].media_asset.model_copy(
        update={"id": uuid4(), "storage_key": f"test/{uuid4()}"}
    )
    row = scene_row(asset)
    generate_row_templates(row, services(SceneModel()), unlimited(), RESERVE)
    with engine.begin() as connection:
        connection.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
        connection.execute(
            insert(preloaded_scenes).values(
                {key: row[key] for key in row if key != "id"}
            )
        )
    yield engine, owner, profile, client, asset, row
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.scene_media_asset_id == asset.id))
        connection.execute(delete(preloaded_scenes).where(preloaded_scenes.c.slug == row["slug"]))
        connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))


def run(curated, model, key, accept=None, **changes):
    engine, owner, profile, client, asset, _ = curated
    response = client.post(
        "/api/v1/sessions",
        json={
            "languageProfileId": str(profile.id),
            "mediaAssetId": str(asset.id),
            "idempotencyKey": key,
        },
    )
    assert response.status_code == 202, response.text
    session_id = UUID(response.json()["session"]["id"])
    feature = services(model)
    repo = PostgresWorkflowRepository(
        engine,
        owner.id,
        translator=feature["translation"],
        learning_task_generator=feature["lessons"],
        ispy_clue_generator=feature["clues"],
    )
    repo.analyze(session_id, profile.id)
    detail = repo.get(session_id, profile.id)
    accepted = detail.scene_objects if accept is None else detail.scene_objects[:accept]
    ids = {obj.id for obj in accepted}
    # Like the review screen: resend the suggested attributes and relations.
    request = {
        "acceptedObjectIds": [str(obj.id) for obj in accepted],
        "objectAttributes": {
            str(obj.id): obj.attributes for obj in accepted if obj.attributes
        },
        "relations": [
            row.model_dump(mode="json", by_alias=True)
            for row in detail.scene_object_relations
            if {row.subject_scene_object_id, row.reference_scene_object_id} <= ids
        ],
        **changes,
    }
    repo.review(session_id, profile.id, ReviewPracticeRequest.model_validate(request))
    with engine.begin() as connection:
        rows = connection.execute(
            select(session_tasks).where(session_tasks.c.session_id == session_id)
        ).mappings().all()
    return session_id, [dict(row) for row in rows]


def test_unchanged_scene_builds_fresh_tasks_from_templates_without_calls(curated):
    model = SceneModel(error=AssertionError("provider must not be called"))
    first, first_tasks = run(curated, model, "template-one")
    client = curated[3]
    assert client.post(f"/api/v1/sessions/{first}/abandon").status_code == 200
    second, second_tasks = run(curated, model, "template-two")
    assert model.requests == []
    for tasks in (first_tasks, second_tasks):
        text = str(tasks)
        assert "Gender and number agreement" in text
        assert "debajo de algo rojo" in text
    assert {task["id"] for task in first_tasks}.isdisjoint(
        {task["id"] for task in second_tasks}
    )
    assert {task["session_id"] for task in first_tasks} == {first}


def test_template_answers_stay_out_of_public_scene_responses(curated):
    *_, client, _, row = curated
    for path in ("/api/v1/preloaded-scenes", f"/api/v1/preloaded-scenes/{row['slug']}"):
        response = client.get(path)
        assert response.status_code == 200
        assert "generated" not in response.text
        assert "debajo de algo rojo" not in response.text


def test_edited_scene_uses_routed_generation(curated):
    model = SceneModel()
    run(
        curated, model, "template-edited",
        addedObjects=[{"id": str(uuid4()), "label": "my diary", "x": 0.5, "y": 0.5}],
    )
    assert "scene_translation_v1" in model.requests


def test_partial_selection_uses_routed_generation(curated):
    model = SceneModel()
    run(curated, model, "template-partial", accept=1)
    assert "scene_translation_v1" in model.requests
