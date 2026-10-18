"""Retained failed sessions, generation retry and lesson-check outcomes."""

from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from test_mission_m01_stage2 import MultilingualModel, enable_m01, make_ko, use_repository
from test_mission_m01_workflow import _answer_key, _lesson
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.vocabulary import user_vocabulary_progress, vocabulary_encounters
from app.repositories.postgres.workflow import MAX_ANALYSIS_ATTEMPTS
from app.repositories.postgres.xp import xp_events
from app.schemas.sessions import Session
from app.services import mission_eligibility


def _count(engine, table, *where):
    with engine.connect() as connection:
        return connection.execute(
            select(func.count()).select_from(table).where(*where)
        ).scalar_one()


def _failed_m01(curated, monkeypatch):
    enable_m01(monkeypatch)
    make_ko(curated)
    model = MultilingualModel("invalid")
    repository, session_id, detail = _lesson(curated, model)
    use_repository(curated[3], repository)
    return repository, session_id, detail, model


def _counts(engine, owner_id, session_id):
    return {
        "tasks": _count(engine, session_tasks, session_tasks.c.session_id == session_id),
        "encounters": _count(
            engine, vocabulary_encounters, vocabulary_encounters.c.session_id == session_id
        ),
        "progress": _count(
            engine, user_vocabulary_progress, user_vocabulary_progress.c.user_id == owner_id
        ),
        "xp": _count(engine, xp_events, xp_events.c.user_id == owner_id),
    }


def test_failed_m01_keeps_the_photo_review_and_translation(curated, monkeypatch):
    engine, owner, _profile, client, asset, _ = curated
    _repository, session_id, detail, _model = _failed_m01(curated, monkeypatch)

    assert detail.session.status == "failed"
    assert detail.session.failure_code == "taskGenerationFailed"
    assert detail.generation_retryable is True
    assert detail.analysis_retryable is False
    assert detail.media_asset.id == asset.id
    assert detail.session.scene_confirmed_at is not None
    assert detail.scene_objects
    assert detail.session.analysis_draft["translationPreview"]["objects"]
    assert "generationRetry" not in detail.session.analysis_draft
    assert _counts(engine, owner.id, session_id)["encounters"] > 0
    assert not any(task.kind == "grammarLesson" for task in detail.tasks)

    body = client.get(f"/api/v1/sessions/{session_id}").json()
    assert body["generationRetryable"] is True
    assert body["analysisRetryable"] is False
    # Like analysis-retryable sessions, a failed session is not the active practice.
    assert client.get("/api/v1/sessions/active").json() is None


def test_retry_regenerates_from_the_saved_review_without_duplicates(curated, monkeypatch):
    engine, owner, _profile, client, *_ = curated
    repository, session_id, _detail, model = _failed_m01(curated, monkeypatch)
    before = _counts(engine, owner.id, session_id)
    translations = model.requests.count("scene_translation_v1")
    model.mode = "valid"

    response = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
    assert response.status_code == 200, response.text
    assert response.json()["session"]["status"] == "generatingTasks"
    assert response.json()["session"]["failureCode"] is None

    detail = repository.get(session_id)
    assert detail.session.status == "inProgress"
    assert detail.generation_retryable is False
    assert detail.session.analysis_draft["generationAttempts"] == 2
    assert "generationRetry" not in detail.session.analysis_draft
    assert model.requests.count("scene_translation_v1") == translations
    m01 = [task for task in detail.tasks if task.public_content.mission_id == "M01"]
    assert len(m01) == 1
    assert len({task.id for task in detail.tasks}) == len(detail.tasks)
    after = _counts(engine, owner.id, session_id)
    assert after["tasks"] == len(detail.tasks) == before["tasks"] + 1
    assert {key: after[key] for key in ("encounters", "progress", "xp")} == {
        key: before[key] for key in ("encounters", "progress", "xp")
    }

    repeated = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
    assert repeated.status_code == 409
    assert _counts(engine, owner.id, session_id) == after


def test_generation_retry_stops_after_the_attempt_cap(curated, monkeypatch):
    _engine, _owner, _profile, client, *_ = curated
    _repository, session_id, _detail, model = _failed_m01(curated, monkeypatch)

    for attempt in range(2, MAX_ANALYSIS_ATTEMPTS + 1):
        response = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
        assert response.status_code == 200, response.text
        body = client.get(f"/api/v1/sessions/{session_id}").json()
        assert body["session"]["status"] == "failed"
        assert body["session"]["analysisDraft"]["generationAttempts"] == attempt
        assert body["generationRetryable"] is (attempt < MAX_ANALYSIS_ATTEMPTS)

    assert model.m01_calls == 2 * MAX_ANALYSIS_ATTEMPTS
    exhausted = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
    assert exhausted.status_code == 409
    assert "practice_conflict" in exhausted.text
    # Leaving stays limited to retryable failures.
    assert client.post(f"/api/v1/sessions/{session_id}/abandon").status_code == 409


def test_a_generation_retryable_session_can_be_left(curated, monkeypatch):
    _engine, _owner, _profile, client, *_ = curated
    _repository, session_id, _detail, _model = _failed_m01(curated, monkeypatch)

    response = client.post(f"/api/v1/sessions/{session_id}/abandon")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "abandoned"
    body = client.get(f"/api/v1/sessions/{session_id}").json()
    assert body["session"]["status"] == "abandoned"
    assert body["generationRetryable"] is False
    assert client.post(f"/api/v1/sessions/{session_id}/retry-analysis").status_code == 409


def test_generation_retry_respects_open_practice_limits(curated, monkeypatch):
    engine, _owner, profile, client, *_ = curated
    _repository, session_id, detail, _model = _failed_m01(curated, monkeypatch)
    open_session = Session(
        user_id=profile.user_id,
        language_profile_id=profile.id,
        scene_media_asset_id=detail.session.scene_media_asset_id,
        status="awaitingObjectReview",
    )
    with engine.begin() as connection:
        connection.execute(insert(sessions).values(**open_session.model_dump(by_alias=False)))
    same_photo = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
    assert same_photo.status_code == 409
    assert "practice_conflict" in same_photo.text
    with engine.begin() as connection:
        for _ in range(2):
            extra = open_session.model_copy(update={"id": uuid4()})
            connection.execute(insert(sessions).values(**extra.model_dump(by_alias=False)))
    limited = client.post(f"/api/v1/sessions/{session_id}/retry-analysis")
    assert limited.status_code == 409
    assert "active_session_limit_reached" in limited.text
    assert client.get(f"/api/v1/sessions/{session_id}").json()["session"]["status"] == "failed"


def test_regular_lesson_check_without_evaluations_has_no_outcome(curated, monkeypatch):
    engine, _owner, _profile, client, *_ = curated
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", ())
    repository, _session_id, detail = _lesson(curated, SceneModel())
    use_repository(client, repository)
    assert detail.session.status == "inProgress"
    lesson = next(
        task for task in detail.tasks
        if task.kind == "grammarLesson" and task.public_content.mission_id is None
    )
    key = _answer_key(engine, lesson.id)
    assert not key.get("questionEvaluations")
    question_id = lesson.public_content.questions[0].question_id

    response = client.post(f"/api/v1/tasks/{lesson.id}/check-lesson-answer", json={
        "questionId": question_id, "answer": key["correctOptionIds"][question_id],
    })
    assert response.status_code == 200, response.text
    assert response.json()["isCorrect"] is True
    assert "outcome" not in response.json()
    checks = client.get(f"/api/v1/tasks/{lesson.id}/lesson-checks")
    assert checks.status_code == 200, checks.text
    assert [item.get("outcome") for item in checks.json()["checks"]] == [None]


def test_mission_question_without_an_evaluation_is_a_conflict(curated, monkeypatch):
    engine, _owner, _profile, client, *_ = curated
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (("M01", "A1", 1),))
    repository, session_id, detail = _lesson(curated, SceneModel())
    use_repository(client, repository)
    mission = next(task for task in detail.tasks if task.public_content.mission_id == "M01")
    key = _answer_key(engine, mission.id)
    assert key.pop("questionEvaluations")
    with engine.begin() as connection:
        connection.execute(
            update(session_tasks).where(session_tasks.c.id == mission.id).values(answer_key=key)
        )
    question_id = mission.public_content.questions[0].question_id

    response = client.post(f"/api/v1/tasks/{mission.id}/check-lesson-answer", json={
        "questionId": question_id, "answer": key["correctOptionIds"][question_id],
    })
    assert response.status_code == 409, response.text
    assert "practice_conflict" in response.text
    draft = repository.get(UUID(str(session_id))).session.analysis_draft
    assert not (draft.get("missionChecks") or {}).get(str(mission.id))
