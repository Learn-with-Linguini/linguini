from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select, update
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.users import users
from app.schemas.users import LanguageProfile, User
from app.services.scene_analysis import DeterministicSceneAnalyzer


def test_analyzer_runs_once_and_review_state_never_reanalyzes(database, monkeypatch):
    _, _, profile, client = database
    calls = []
    original = DeterministicSceneAnalyzer.analyze

    def counting(analyzer, *args):
        calls.append(1)
        return original(analyzer, *args)

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", counting)
    sid = create_run(client, profile)["session"]["id"]
    first = client.post(f"/api/v1/sessions/{sid}/analyze")
    assert first.status_code == 200, first.text
    # Curated scenes use their saved analysis and are ready for review directly.
    assert first.json()["session"]["status"] == "awaitingObjectReview"
    repeat = client.post(f"/api/v1/sessions/{sid}/analyze")
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["session"]["status"] == "awaitingObjectReview"
    assert len(calls) == 1


def test_repeated_analysis_returns_identical_draft(database):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 200
    first = client.get(f"/api/v1/sessions/{sid}").json()
    repeat = client.post(f"/api/v1/sessions/{sid}/analyze").json()
    assert repeat["session"]["status"] == "awaitingObjectReview"
    assert repeat["sceneObjects"] == first["sceneObjects"]
    assert repeat["sceneObjectRelations"] == first["sceneObjectRelations"]
    again = client.get(f"/api/v1/sessions/{sid}").json()
    assert again["sceneObjects"] == first["sceneObjects"]
    assert again["sceneObjectRelations"] == first["sceneObjectRelations"]


def test_concurrent_analyze_invokes_analyzer_at_most_once(database, monkeypatch):
    _, _, profile, client = database
    calls = []
    original = DeterministicSceneAnalyzer.analyze

    def counting(analyzer, *args):
        calls.append(1)
        return original(analyzer, *args)

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", counting)
    sid = create_run(client, profile)["session"]["id"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(
            pool.map(lambda _: client.post(f"/api/v1/sessions/{sid}/analyze"), range(3))
        )
    assert all(response.status_code == 200 for response in responses)
    assert all(
        response.json()["session"]["status"] in {"analyzingScene", "awaitingObjectReview"}
        for response in responses
    )
    assert len(calls) <= 1
    settled = client.get(f"/api/v1/sessions/{sid}").json()
    assert settled["session"]["status"] == "awaitingObjectReview"


def test_analyze_is_scoped_to_the_owner(database, monkeypatch):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    stranger = User(display_name="Other learner", auth_provider_id=f"stranger-{uuid4()}")
    with engine.begin() as c:
        c.execute(insert(users).values(**stranger.model_dump(by_alias=False)))
    try:
        PostgresLanguageProfileRepository(engine).create(
            LanguageProfile(
                user_id=stranger.id,
                source_language_code="en",
                target_language_code="es",
                proficiency_level="A1",
            )
        )
        monkeypatch.setenv("DEMO_USER_ID", str(stranger.id))
        assert client.get(f"/api/v1/sessions/{sid}").status_code == 404
        assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 404
    finally:
        with engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.user_id == stranger.id))
            c.execute(delete(users).where(users.c.id == stranger.id))


def test_analyze_persists_title_summary_and_draft(database):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    claimed = client.post(f"/api/v1/sessions/{sid}/analyze").json()
    assert claimed["session"]["status"] == "awaitingObjectReview"
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    objects = detail["sceneObjects"]
    relations = detail["sceneObjectRelations"]
    assert objects and relations
    ids = {obj["id"] for obj in objects}
    for relation in relations:
        assert relation["subjectSceneObjectId"] in ids
        assert relation["referenceSceneObjectId"] in ids
        assert relation["sourceRelationKey"].startswith("deterministic-v1:")
    saved = client.get(f"/api/v1/sessions/{sid}").json()["session"]
    assert saved["sessionTitle"]
    assert saved["sessionSummary"]


def test_analyzer_failure_marks_session_failed(database, monkeypatch):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]

    def fail(*args):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", fail)
    # A provider failure surfaces as a failed session, not a request error.
    response = client.post(f"/api/v1/sessions/{sid}/analyze")
    assert response.status_code == 200, response.text
    assert response.json()["session"]["status"] == "failed"
    session = client.get(f"/api/v1/sessions/{sid}").json()["session"]
    assert session["status"] == "failed"
    assert session["failureCode"] == "sceneAnalysisFailed"
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 409


def test_analyze_rejects_sessions_past_review(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 200
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    accepted = [obj["id"] for obj in detail["sceneObjects"]]
    reviewed = client.put(f"/api/v1/sessions/{sid}/review", json={"acceptedObjectIds": accepted})
    assert reviewed.status_code == 200, reviewed.text
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 409
    for task in client.get(f"/api/v1/sessions/{sid}").json()["tasks"]:
        assert client.post(f"/api/v1/tasks/{task['id']}/skip", json={}).status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/complete").status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 409
    abandoned = create_run(client, profile, "abandoned-session-key")["session"]["id"]
    assert client.post(f"/api/v1/sessions/{abandoned}/abandon").status_code == 200
    assert client.post(f"/api/v1/sessions/{abandoned}/analyze").status_code == 409
    failed = create_run(client, profile, "failed-session-key")["session"]["id"]
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.id == UUID(failed)).values(status="failed"))
    assert client.post(f"/api/v1/sessions/{failed}/analyze").status_code == 409
    ready = create_run(client, profile, "ready-session-key")["session"]["id"]
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.id == UUID(ready)).values(status="ready"))
    assert client.post(f"/api/v1/sessions/{ready}/analyze").status_code == 409
    with engine.begin() as c:
        assert (
            c.execute(select(sessions.c.status).where(sessions.c.id == UUID(ready))).scalar_one()
            == "ready"
        )
