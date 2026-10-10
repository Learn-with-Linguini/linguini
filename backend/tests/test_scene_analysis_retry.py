from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.users import users
from app.repositories.postgres.workflow import MAX_ANALYSIS_ATTEMPTS
from app.schemas.sessions import Session
from app.schemas.users import LanguageProfile, User
from app.services.scene_analysis import DeterministicSceneAnalyzer

ORIGINAL = DeterministicSceneAnalyzer.analyze


class ModerationRejected(RuntimeError):
    code = "imageModerationFailed"


def provider_failure(*args):
    raise RuntimeError("provider unavailable")


def failed_run(client, profile, monkeypatch, key="retry-session-key"):
    sid = create_run(client, profile, key)["session"]["id"]
    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", provider_failure)
    failed = client.post(f"/api/v1/sessions/{sid}/analyze").json()
    assert failed["session"]["status"] == "failed"
    assert failed["session"]["failureCode"] == "sceneAnalysisFailed"
    assert failed["analysisRetryable"] is True
    return sid, failed


def asset_count(engine):
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(media_assets)).scalar_one()


def test_retry_reanalyzes_the_saved_image(database, monkeypatch):
    engine, _, profile, client = database
    sid, failed = failed_run(client, profile, monkeypatch)
    assets_before = asset_count(engine)
    seen = []

    def recovered(analyzer, session, asset, *args):
        seen.append(asset.id)
        return ORIGINAL(analyzer, session, asset, *args)

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", recovered)
    response = client.post(f"/api/v1/sessions/{sid}/retry-analysis")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["session"]["status"] == "awaitingObjectReview"
    assert detail["session"]["failureCode"] is None
    assert detail["analysisRetryable"] is False
    assert detail["sceneObjects"]
    assert detail["session"]["sceneMediaAssetId"] == failed["session"]["sceneMediaAssetId"]
    assert seen == [UUID(failed["session"]["sceneMediaAssetId"])]
    assert asset_count(engine) == assets_before
    assert client.post(f"/api/v1/sessions/{sid}/retry-analysis").status_code == 200


def test_repeated_failures_stop_after_the_attempt_cap(database, monkeypatch):
    _, _, profile, client = database
    sid, _ = failed_run(client, profile, monkeypatch)
    calls = []

    def failing(*args):
        calls.append(1)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", failing)
    for attempt in range(2, MAX_ANALYSIS_ATTEMPTS + 1):
        detail = client.post(f"/api/v1/sessions/{sid}/retry-analysis").json()
        assert detail["session"]["status"] == "failed"
        assert detail["session"]["failureCode"] == "sceneAnalysisFailed"
        assert detail["analysisRetryable"] is (attempt < MAX_ANALYSIS_ATTEMPTS)
    assert len(calls) == MAX_ANALYSIS_ATTEMPTS - 1
    assert client.post(f"/api/v1/sessions/{sid}/retry-analysis").status_code == 409
    assert len(calls) == MAX_ANALYSIS_ATTEMPTS - 1


def test_moderation_rejection_is_not_retryable(database, monkeypatch):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]

    def rejected(*args):
        raise ModerationRejected("blocked")

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", rejected)
    detail = client.post(f"/api/v1/sessions/{sid}/analyze").json()
    assert detail["session"]["failureCode"] == "imageModerationFailed"
    assert detail["analysisRetryable"] is False
    assert client.post(f"/api/v1/sessions/{sid}/retry-analysis").status_code == 409


def test_only_scene_analysis_failures_can_retry(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    for code in ("taskGenerationFailed", "noValidObjects"):
        with engine.begin() as c:
            c.execute(
                update(sessions)
                .where(sessions.c.id == UUID(sid))
                .values(status="failed", failure_code=code)
            )
        assert client.get(f"/api/v1/sessions/{sid}").json()["analysisRetryable"] is False
        assert client.post(f"/api/v1/sessions/{sid}/retry-analysis").status_code == 409
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 409


def test_expired_analysis_without_attempt_count_can_retry(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    with engine.begin() as c:
        c.execute(
            update(sessions)
            .where(sessions.c.id == UUID(sid))
            .values(status="failed", failure_code="sceneAnalysisFailed", analysis_draft=None)
        )
    assert client.get(f"/api/v1/sessions/{sid}").json()["analysisRetryable"] is True
    detail = client.post(f"/api/v1/sessions/{sid}/retry-analysis").json()
    assert detail["session"]["status"] == "awaitingObjectReview"


def test_failed_session_stays_out_of_active_practice(database, monkeypatch):
    _, _, profile, client = database
    failed_run(client, profile, monkeypatch)
    assert client.get("/api/v1/sessions/active").json() is None


def test_retry_respects_open_practice_limits(database, monkeypatch):
    engine, _, profile, client = database
    sid, failed = failed_run(client, profile, monkeypatch)
    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", ORIGINAL)
    open_session = Session(
        user_id=profile.user_id,
        language_profile_id=profile.id,
        scene_media_asset_id=UUID(failed["session"]["sceneMediaAssetId"]),
        status="awaitingObjectReview",
    )
    with engine.begin() as c:
        c.execute(insert(sessions).values(**open_session.model_dump(by_alias=False)))
    same_photo = client.post(f"/api/v1/sessions/{sid}/retry-analysis")
    assert same_photo.status_code == 409
    assert "practice_conflict" in same_photo.text
    with engine.begin() as c:
        for _ in range(2):
            extra = open_session.model_copy(update={"id": uuid4()})
            c.execute(insert(sessions).values(**extra.model_dump(by_alias=False)))
    limited = client.post(f"/api/v1/sessions/{sid}/retry-analysis")
    assert limited.status_code == 409
    assert "active_session_limit_reached" in limited.text
    assert client.get(f"/api/v1/sessions/{sid}").json()["session"]["status"] == "failed"


def test_concurrent_retries_run_analysis_once(database, monkeypatch):
    _, _, profile, client = database
    sid, _ = failed_run(client, profile, monkeypatch)
    calls = []

    def counting(analyzer, *args):
        calls.append(1)
        return ORIGINAL(analyzer, *args)

    monkeypatch.setattr(DeterministicSceneAnalyzer, "analyze", counting)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(
            pool.map(lambda _: client.post(f"/api/v1/sessions/{sid}/retry-analysis"), range(3))
        )
    assert all(response.status_code == 200 for response in responses)
    assert len(calls) == 1
    assert client.get(f"/api/v1/sessions/{sid}").json()["session"]["status"] == (
        "awaitingObjectReview"
    )


def test_retry_is_scoped_to_the_owner(database, monkeypatch):
    engine, _, profile, client = database
    sid, _ = failed_run(client, profile, monkeypatch)
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
        assert client.post(f"/api/v1/sessions/{sid}/retry-analysis").status_code == 404
    finally:
        with engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.user_id == stranger.id))
            c.execute(delete(users).where(users.c.id == stranger.id))
    monkeypatch.setenv("DEMO_USER_ID", str(profile.user_id))
    assert client.get(f"/api/v1/sessions/{sid}").json()["session"]["status"] == "failed"
