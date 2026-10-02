from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from test_postgres_sessions import database as database

from app.repositories.postgres.media_assets import PostgresMediaAssetRepository, media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_objects
from app.repositories.postgres.tasks import session_tasks
from app.schemas.media import MediaAsset


def test_analysis_persistence_concurrency_and_review(database):
    engine, owner, profile, client = database
    asset = MediaAsset(
        owner_user_id=owner.id,
        source="camera",
        media_type="image",
        storage_key=f"test/{uuid4()}.jpg",
        mime_type="image/jpeg",
    )
    PostgresMediaAssetRepository(engine).create(asset)
    try:
        payload = {
            "languageProfileId": str(profile.id),
            "mediaAssetId": str(asset.id),
            "idempotencyKey": "uploaded-analysis-test",
        }
        created = client.post("/api/v1/sessions", json=payload)
        assert created.status_code == 202, created.text
        sid = created.json()["session"]["id"]
        assert client.post("/api/v1/sessions", json=payload).json()["session"]["id"] == sid
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(
                pool.map(lambda _: client.post(f"/api/v1/sessions/{sid}/analyze"), range(3))
            )
        assert all(r.status_code == 200 for r in responses)
        detail = client.get(f"/api/v1/sessions/{sid}").json()
        assert len(detail["sceneObjects"]) == 3
        oid = detail["sceneObjects"][0]["id"]
        assert not detail["tasks"]
        with engine.connect() as c:
            assert not c.execute(
                select(scene_objects).where(scene_objects.c.session_id == UUID(sid))
            ).first()
            assert not c.execute(
                select(session_tasks).where(session_tasks.c.session_id == UUID(sid))
            ).first()
        assert (
            client.get(f"/api/v1/sessions/{sid}").json()["sceneObjects"] == detail["sceneObjects"]
        )
        unknown = {
            "acceptedObjectIds": [oid],
            "addedObjects": [
                {"id": str(uuid4()), "label": "missing-catalog-word", "x": 0.3, "y": 0.4}
            ],
        }
        assert client.put(f"/api/v1/sessions/{sid}/review", json=unknown).status_code == 409
        with engine.connect() as c:
            assert not c.execute(
                select(scene_objects).where(scene_objects.c.session_id == UUID(sid))
            ).first()
        accepted = [o["id"] for o in detail["sceneObjects"] if o["id"] != oid]
        saved = client.put(f"/api/v1/sessions/{sid}/review", json={"acceptedObjectIds": accepted})
        assert saved.status_code == 200, saved.text
        retry = client.post(f"/api/v1/sessions/{sid}/analyze")
        assert retry.status_code == 409
        persisted = client.get(f"/api/v1/sessions/{sid}").json()
        assert {o["id"] for o in persisted["sceneObjects"]} == set(accepted)
        assert persisted["tasks"]
        assert client.post(f"/api/v1/sessions/{sid}/abandon").status_code == 200
        assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 409
        assert UUID(sid)
    finally:
        with engine.begin() as connection:
            connection.execute(delete(sessions).where(sessions.c.scene_media_asset_id == asset.id))
            connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))
