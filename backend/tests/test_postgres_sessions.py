import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.database import create_database_engine
from app.main import create_app
from app.repositories.postgres.language_profiles import (
    PostgresLanguageProfileRepository,
)
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import user_vocabulary_progress, vocabulary_encounters
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import award
from app.repositories.practice import PracticeConflictError
from app.schemas.base import utc_now
from app.schemas.enums import TaskKind
from app.schemas.media import MediaAsset
from app.schemas.users import LanguageProfile, User


@pytest.fixture
def database(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    if os.getenv("TEST_DATABASE_SCHEMA"):
        engine = engine.execution_options(
            schema_translate_map={"public": os.environ["TEST_DATABASE_SCHEMA"]}
        )
        monkeypatch.setattr("app.main.create_database_engine", lambda: engine)
    monkeypatch.setenv("MEDIA_STORAGE_PRIVATE", "false")
    owner = User(display_name="Sessions test", auth_provider_id=f"test-{uuid4()}")
    monkeypatch.setenv("DEMO_USER_ID", str(owner.id))
    with engine.begin() as connection:
        connection.execute(insert(users).values(**owner.model_dump(by_alias=False)))
    profile = PostgresLanguageProfileRepository(engine).create(
        LanguageProfile(
            user_id=owner.id,
            source_language_code="en",
            target_language_code="es",
            proficiency_level="A1",
        )
    )
    app = create_app()
    # Surface the underlying database error in tests instead of a generic HTTP 500.
    from app.repositories.practice import PracticeStorageError

    async def storage_failure(_request, exc):
        raise exc

    app.add_exception_handler(PracticeStorageError, storage_failure)
    with TestClient(app) as client:
        from app.services.background import InlineBackgroundRunner

        app.state.background_runner = InlineBackgroundRunner()
        yield engine, owner, profile, client
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.user_id == owner.id))
        connection.execute(delete(media_assets).where(media_assets.c.owner_user_id == owner.id))
        connection.execute(delete(users).where(users.c.id == owner.id))
    engine.dispose()


def create_run(client, profile, key="session-key-1"):
    scenes = client.get("/api/v1/preloaded-scenes").json()
    scene = next(row for row in scenes if row.get("languageCode", "es") == "es")
    response = client.post(
        "/api/v1/sessions",
        json={
            "languageProfileId": str(profile.id),
            "mediaAssetId": scene["mediaAsset"]["id"],
            "idempotencyKey": key,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def vocabulary_answer(content, correct=True):
    """Grouped lessons are answered in one attempt covering every question."""
    return {
        "inputMode": "vocabularyReview",
        "answers": {
            question["questionId"]: question["options"][0 if correct else -1]["optionId"]
            for question in content["questions"]
        },
    }


def analyze(client, sid, confirm=True):
    response = client.post(f"/api/v1/sessions/{sid}/analyze")
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    if confirm and not detail["tasks"]:
        response = client.put(
            f"/api/v1/sessions/{sid}/review",
            json={"acceptedObjectIds": [detail["sceneObjects"][0]["id"]]},
        )
        assert response.status_code == 200, response.text
        detail = client.get(f"/api/v1/sessions/{sid}").json()
    return detail


def test_progress_returns_a_current_local_streak(database):
    engine, owner, profile, client = database
    with engine.begin() as connection:
        award(
            connection,
            user_id=owner.id,
            language_profile_id=profile.id,
            event_type="taskCompleted",
            idempotency_key="streak-yesterday",
            occurred_at=utc_now() - timedelta(days=1),
        )
        award(
            connection,
            user_id=owner.id,
            language_profile_id=profile.id,
            event_type="journalEntry",
            idempotency_key="streak-today",
        )

    streak = client.get("/api/v1/me/progress").json()["streak"]
    assert len(streak["days"]) == 7
    assert streak["current"] == 2
    assert [day["active"] for day in streak["days"][-2:]] == [True, True]


@pytest.mark.parametrize("source", ["preloaded", "userUpload", "camera"])
def test_normalized_workflow_and_idempotent_progress(database, source):
    engine, owner, profile, client = database
    if source == "preloaded":
        run = create_run(client, profile)
        assert create_run(client, profile)["session"]["id"] == run["session"]["id"]
    else:
        asset = MediaAsset(
            owner_user_id=owner.id,
            source=source,
            media_type="image",
            storage_key=f"users/{owner.id}/images/{uuid4()}.jpg",
            mime_type="image/jpeg",
        )
        with engine.begin() as c:
            c.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
        response = client.post(
            "/api/v1/sessions",
            json={
                "languageProfileId": str(profile.id),
                "mediaAssetId": str(asset.id),
                "idempotencyKey": "upload-session-key",
            },
        )
        assert response.status_code == 202, response.text
        run = response.json()
    sid = run["session"]["id"]
    endpoint = f"/api/v1/sessions/{sid}"
    assert run["tasks"] == []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: analyze(client, sid, confirm=False), range(4)))
    assert all(not result["tasks"] for result in results)
    assert all(
        result["session"]["status"] in {"analyzingScene", "awaitingObjectReview"}
        for result in results
    )
    settled = client.get(f"/api/v1/sessions/{sid}").json()
    assert settled["session"]["status"] == "awaitingObjectReview"
    assert settled["sceneObjects"]
    detail = analyze(client, sid)
    # Without a learning-task generator the plan is the deterministic fallback.
    planned = {kind.value for kind in TaskKind} - {TaskKind.GRAMMAR_LESSON.value}
    assert len(detail["tasks"]) == len(planned)
    assert {t["kind"] for t in detail["tasks"]} == planned
    assert all(o["vocabularyItemId"] for o in detail["sceneObjects"])
    assert "answerKey" not in str(detail) and "demoState" not in detail
    assert client.get("/api/v1/me/progress").json()["xp"] == 0
    assert client.post(endpoint + "/complete").status_code == 409
    tasks = detail["tasks"]
    intro = tasks[0]
    answer = vocabulary_answer(intro["publicContent"]) | {"idempotencyKey": "same-attempt-key"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        evaluated = list(
            pool.map(
                lambda _: client.post(f"/api/v1/tasks/{intro['id']}/attempts", json=answer),
                range(4),
            )
        )
    assert all(r.status_code == 200 for r in evaluated), [r.text for r in evaluated]
    assert len({r.json()["attempt"]["id"] for r in evaluated}) == 1
    assert (
        client.post(
            f"/api/v1/tasks/{intro['id']}/attempts",
            json=answer | vocabulary_answer(intro["publicContent"], correct=False),
        ).status_code
        == 409
    )
    with engine.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(task_attempts)
                .where(task_attempts.c.session_task_id == UUID(intro["id"]))
            ).scalar_one()
            == 1
        )
        events = (
            c.execute(
                select(vocabulary_encounters).where(vocabulary_encounters.c.session_id == UUID(sid))
            )
            .mappings()
            .all()
        )
        assert len(events) == 1
        progress = (
            c.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.user_id == owner.id
                )
            )
            .mappings()
            .one()
        )
        assert progress["exposure_count"] == 1 and progress["correct_attempt_count"] == 1
    for task in tasks[1:]:
        skip = f"/api/v1/tasks/{task['id']}/skip"
        assert client.post(skip, json={}).status_code == 200
        assert client.post(skip, json={}).status_code == 200
    # One completed task earns 10 XP; completing the session adds 20 XP.
    assert client.get("/api/v1/me/progress").json()["xp"] == 10
    assert client.post(endpoint + "/complete").status_code == 200
    assert client.post(endpoint + "/complete").status_code == 200
    summary = client.get(endpoint + "/summary").json()
    assert summary["xpEarned"] == 30
    assert summary["ispyCorrectCount"] == summary["ispyAttemptCount"] == 0
    assert summary["progress"]["completedTaskCount"] == 1
    assert summary["progress"]["skippedTaskCount"] == 6
    assert len(summary["learnedVocabularyIds"]) == 1
    assert client.post(f"/api/v1/tasks/{intro['id']}/skip", json={}).status_code == 409
    with TestClient(create_app()) as restarted:
        assert restarted.get(endpoint).json()["progress"] == summary["progress"]
    assert PostgresWorkflowRepository(engine, uuid4()).active(profile.id) is None


def test_skip_all_adds_no_learning_credit(database):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    detail = analyze(client, sid)
    for task in detail["tasks"]:
        assert client.post(f"/api/v1/tasks/{task['id']}/skip", json={}).status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/complete").status_code == 200
    # Skipped tasks earn nothing; completing the session itself pays 20.
    assert client.get("/api/v1/me/progress").json()["xp"] == 20
    assert client.get("/api/v1/me/vocabulary").json()["items"] == []
    summary = client.get(f"/api/v1/sessions/{sid}/summary").json()
    assert summary["xpEarned"] == 20
    assert summary["ispyCorrectCount"] == summary["ispyAttemptCount"] == 0


def test_task_updates_roll_back_with_encounter_failure(database, monkeypatch):
    engine, owner, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    detail = analyze(client, sid)

    def fail(*args, **kwargs):
        raise RuntimeError("Simulated progress write failure")

    intro = detail["tasks"][0]
    with monkeypatch.context() as patcher:
        patcher.setattr(PostgresWorkflowRepository, "_encounter", fail)
        with pytest.raises(RuntimeError):
            client.post(
                f"/api/v1/tasks/{intro['id']}/attempts",
                json=vocabulary_answer(intro["publicContent"]),
            )
    with engine.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(task_attempts)
                .where(task_attempts.c.session_task_id == UUID(intro["id"]))
            ).scalar_one()
            == 0
        )
    assert client.get(f"/api/v1/sessions/{sid}").json()["tasks"][0]["status"] == "pending"


def upload_asset(engine, owner):
    asset = MediaAsset(
        owner_user_id=owner.id,
        source="userUpload",
        media_type="image",
        storage_key=f"users/{owner.id}/images/{uuid4()}.jpg",
        mime_type="image/jpeg",
    )
    with engine.begin() as c:
        c.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
    return asset.id


def create_with_asset(client, profile, asset_id, key):
    return client.post(
        "/api/v1/sessions",
        json={
            "languageProfileId": str(profile.id),
            "mediaAssetId": str(asset_id),
            "idempotencyKey": key,
        },
    )


def age_session(engine, session_id, status, processing_started_at):
    with engine.begin() as c:
        c.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                status=status,
                analysis_draft={"processingStartedAt": processing_started_at.isoformat()},
            )
        )


def test_multiple_active_sessions_and_owner_scope(database, monkeypatch):
    engine, owner, profile, client = database
    first = create_run(client, profile)["session"]["id"]
    # The same image under a different key continues the open run.
    continued = create_run(client, profile, "replacement-key")
    assert continued["session"]["id"] == first
    assert client.get(f"/api/v1/sessions/{first}").json()["session"]["status"] == "created"
    # A different image creates another unfinished session.
    asset = upload_asset(engine, owner)
    second_response = create_with_asset(client, profile, asset, "other-asset-key")
    assert second_response.status_code == 202, second_response.text
    second = second_response.json()["session"]["id"]
    third_asset = upload_asset(engine, owner)
    third_response = create_with_asset(client, profile, third_asset, "third-asset-key")
    assert third_response.status_code == 202, third_response.text
    third = third_response.json()["session"]["id"]
    fourth = create_with_asset(client, profile, upload_asset(engine, owner), "fourth-asset-key")
    assert fourth.status_code == 409
    assert fourth.json()["detail"]["code"] == "active_session_limit_reached"
    with engine.connect() as c:
        ids = c.execute(select(sessions.c.id).where(sessions.c.user_id == owner.id)).scalars().all()
    assert set(ids) == {UUID(first), UUID(second), UUID(third)}

    # The state machine rejects edges outside ALLOWED_TRANSITIONS.
    repository = PostgresWorkflowRepository(engine, owner.id)
    with repository.transaction() as connection:
        session = repository._session(connection, UUID(first))
        with pytest.raises(PracticeConflictError):
            repository._transition(connection, session, "completed")

    # created -> analyzingScene -> awaitingObjectReview -> generatingTasks -> inProgress.
    assert client.post(f"/api/v1/sessions/{first}/analyze").status_code == 200
    detail = client.get(f"/api/v1/sessions/{first}").json()
    assert detail["session"]["status"] == "awaitingObjectReview"
    reviewed = client.put(
        f"/api/v1/sessions/{first}/review",
        json={"acceptedObjectIds": [detail["sceneObjects"][0]["id"]]},
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed = client.get(f"/api/v1/sessions/{first}").json()
    assert reviewed["session"]["status"] == "inProgress"
    assert reviewed["session"]["startedAt"] is not None
    for task in reviewed["tasks"]:
        assert client.post(f"/api/v1/tasks/{task['id']}/skip", json={}).status_code == 200
    assert client.post(f"/api/v1/sessions/{first}/complete").status_code == 200
    completed = client.get(f"/api/v1/sessions/{first}").json()["session"]
    assert completed["status"] == "completed" and completed["completedAt"] is not None

    # The second unfinished session remains available after the first completes.
    assert client.get(f"/api/v1/sessions/{second}").status_code == 200
    assert client.post(f"/api/v1/sessions/{second}/abandon").status_code == 200
    assert client.post(f"/api/v1/sessions/{second}/analyze").status_code == 409
    abandoned = client.get(f"/api/v1/sessions/{second}").json()["session"]
    assert abandoned["status"] == "abandoned" and abandoned["abandonedAt"] is not None
    assert client.post(f"/api/v1/sessions/{third}/abandon").status_code == 200

    created = create_with_asset(client, profile, asset, "other-asset-key-2")
    assert created.status_code == 202, created.text
    replacement = created.json()["session"]["id"]
    assert client.get("/api/v1/sessions/active").json()["session"]["id"] == replacement
    assert client.post(f"/api/v1/sessions/{replacement}/abandon").status_code == 200
    assert client.post(f"/api/v1/sessions/{replacement}/analyze").status_code == 409
    abandoned = client.get(f"/api/v1/sessions/{replacement}").json()["session"]
    assert abandoned["status"] == "abandoned" and abandoned["abandonedAt"] is not None
    third = create_run(client, profile, "third-session-key")
    assert client.get("/api/v1/sessions/active").json()["session"]["id"] == third["session"]["id"]
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(
            update(sessions)
            .where(sessions.c.id == UUID(third["session"]["id"]))
            .values(status="completed")
        )
    monkeypatch.setenv("DEMO_USER_ID", str(uuid4()))
    assert client.get(f"/api/v1/sessions/{replacement}").status_code == 404


def test_reap_fails_stuck_analysis(database):
    engine, owner, profile, client = database
    # A crashed analysis older than 15 minutes is failed, not blocking.
    first = create_run(client, profile)["session"]["id"]
    age_session(engine, UUID(first), "analyzingScene", utc_now() - timedelta(minutes=30))
    asset = upload_asset(engine, owner)
    created = create_with_asset(client, profile, asset, "after-analysis-timeout")
    assert created.status_code == 202, created.text
    assert created.json()["session"]["id"] != first
    with engine.connect() as c:
        old = c.execute(select(sessions).where(sessions.c.id == UUID(first))).mappings().one()
    assert old["status"] == "failed" and old["failure_code"] == "sceneAnalysisFailed"


def test_active_lookup_reaps_expired_analysis(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    assert client.get("/api/v1/sessions/active").json()["session"]["id"] == sid
    age_session(engine, UUID(sid), "analyzingScene", utc_now() - timedelta(minutes=30))
    assert client.get("/api/v1/sessions/active").json() is None
    with engine.connect() as c:
        row = c.execute(select(sessions).where(sessions.c.id == UUID(sid))).mappings().one()
    assert row["status"] == "failed" and row["failure_code"] == "sceneAnalysisFailed"


def test_get_session_reaps_stale_processing(database):
    engine, _, profile, client = database
    # A session stuck past the timeout fails on its own detail read.
    sid = create_run(client, profile)["session"]["id"]
    age_session(engine, UUID(sid), "analyzingScene", utc_now() - timedelta(minutes=30))
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    assert detail["session"]["status"] == "failed"
    assert detail["session"]["failureCode"] == "sceneAnalysisFailed"
    again = client.get(f"/api/v1/sessions/{sid}").json()
    assert again["session"]["status"] == "failed"
    assert again["session"]["failureCode"] == "sceneAnalysisFailed"
    second = create_run(client, profile, "generating-key")["session"]["id"]
    age_session(engine, UUID(second), "generatingTasks", utc_now() - timedelta(minutes=30))
    detail = client.get(f"/api/v1/sessions/{second}").json()
    assert detail["session"]["status"] == "failed"
    assert detail["session"]["failureCode"] == "taskGenerationFailed"
    # A fresh processing session is returned untouched.
    third = create_run(client, profile, "fresh-key")["session"]["id"]
    age_session(engine, UUID(third), "analyzingScene", utc_now())
    assert client.get(f"/api/v1/sessions/{third}").json()["session"]["status"] == "analyzingScene"


def test_all_task_kinds_complete_with_server_evaluation(database):
    engine, owner, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    detail = analyze(client, sid)
    for task in detail["tasks"]:
        endpoint = f"/api/v1/tasks/{task['id']}"
        assert client.post(endpoint + "/start").status_code == 200
        content = task["publicContent"]
        kind = task["kind"]
        if kind in {"grammarExplanation", "syntaxExplanation"}:
            result = client.post(endpoint + "/complete")
        else:
            assert client.post(endpoint + "/complete").status_code == 409
            if kind in {"vocabularyIntroduction", "grammarLesson"}:
                answer = vocabulary_answer(content)
            elif kind == "ispyRound":
                with engine.connect() as c:
                    key = c.execute(
                        select(session_tasks.c.answer_key).where(
                            session_tasks.c.id == UUID(task["id"])
                        )
                    ).scalar_one()
                answer = {
                    "inputMode": "objectSelection",
                    "sceneObjectId": key["correctSceneObjectId"],
                }
            else:
                value = (
                    content.get("targetText") or content.get("sourceText") or "A sample reflection."
                )
                if kind == "grammarPractice":
                    value = "A deliberately incorrect answer"
                answer = {"inputMode": "text", "text": value}
            result = client.post(
                endpoint + "/attempts", json=answer | {"idempotencyKey": "evaluated-once-key"}
            )
        assert result.status_code == 200, result.text
        assert "answerKey" not in result.text
        if kind == "grammarPractice":
            assert result.json()["attempt"]["isCorrect"] is False
    assert client.post(f"/api/v1/sessions/{sid}/complete").status_code == 200
    # 7 completed tasks + correct I-Spy + session completion + clean sweep bonus:
    # 7*10 + 15 + 20 + 10 = 115 XP.
    assert client.get("/api/v1/me/progress").json()["xp"] == 115
    summary = client.get(f"/api/v1/sessions/{sid}/summary").json()
    assert summary["xpEarned"] == 115
    assert summary["ispyCorrectCount"] == summary["ispyAttemptCount"] == 1
    with engine.connect() as c:
        progress = (
            c.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.user_id == owner.id
                )
            )
            .mappings()
            .one()
        )
        assert progress["exposure_count"] == 5
        assert progress["correct_attempt_count"] == 3
    # Planning another session reuses vocabulary and does not credit exposure.
    other = create_run(client, profile, "another-session-key")
    again = analyze(client, other["session"]["id"])
    assert {v["id"] for v in again["vocabulary"]} == {v["id"] for v in detail["vocabulary"]}
    assert client.get("/api/v1/me/progress").json()["xp"] == 115


def test_other_user_cannot_access_sessions_or_tasks(database, monkeypatch):
    engine, owner, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    detail = analyze(client, sid)
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
        task = detail["tasks"][0]["id"]
        assert client.get(f"/api/v1/tasks/{task}").status_code == 404
        assert client.post(f"/api/v1/tasks/{task}/complete").status_code == 404
        assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 404
    finally:
        with engine.begin() as c:
            c.execute(delete(users).where(users.c.id == stranger.id))


def test_review_rejects_adds_and_rebuilds_without_duplicate_objects(database):
    _, _, profile, client = database
    run = create_run(client, profile, "review-session-key")
    sid = run["session"]["id"]
    detail = analyze(client, sid, confirm=False)
    kept = detail["sceneObjects"][0]["id"]
    payload = {
        "acceptedObjectIds": [kept],
        "addedObjects": [
            {
                "id": str(uuid4()),
                "label": detail["sceneObjects"][1]["label"],
                "x": 0.3,
                "y": 0.4,
            }
        ],
    }
    payload["relations"] = [
        {
            "id": str(uuid4()),
            "subjectSceneObjectId": kept,
            "relation": "beside",
            "referenceSceneObjectId": payload["addedObjects"][0]["id"],
            "sourceRelationKey": "client-cannot-claim-ai-provenance",
        }
    ]
    response = client.put(f"/api/v1/sessions/{sid}/review", json=payload)
    assert response.status_code == 200, response.text
    saved = client.get(f"/api/v1/sessions/{sid}").json()
    selected = saved["sceneObjects"]
    assert len(selected) == 2
    relation = saved["sceneObjectRelations"][0]
    assert relation["sourceRelationKey"] is None
    assert relation["subjectSceneObjectId"] == kept
    assert relation["referenceSceneObjectId"] in {obj["id"] for obj in selected}
    assert relation["referenceSceneObjectId"] != payload["addedObjects"][0]["id"]
    assert any(obj["label"] == detail["sceneObjects"][1]["label"] for obj in selected)
    assert all(
        task["sceneObjectId"] in {obj["id"] for obj in selected}
        for task in saved["tasks"]
        if task["sceneObjectId"]
    )
    # The grouped introduction covers every accepted object in one task.
    introductions = [task for task in saved["tasks"] if task["kind"] == "vocabularyIntroduction"]
    assert len(introductions) == 1
    assert len(introductions[0]["publicContent"]["words"]) == 2
    retry = client.put(f"/api/v1/sessions/{sid}/review", json=payload)
    assert retry.status_code == 200, retry.text
    retry = client.get(f"/api/v1/sessions/{sid}").json()
    assert len(retry["sceneObjects"]) == len(saved["sceneObjects"])
    assert retry["sceneObjectRelations"] == saved["sceneObjectRelations"]
    task_id = next(task["id"] for task in saved["tasks"] if task["kind"] == "grammarExplanation")
    assert client.post(f"/api/v1/tasks/{task_id}/complete", json={}).status_code == 200
    assert client.put(f"/api/v1/sessions/{sid}/review", json=payload).status_code == 409
    persisted = client.get(f"/api/v1/sessions/{sid}").json()
    assert (
        next(task for task in persisted["tasks"] if task["id"] == task_id)["status"] == "completed"
    )
