"""Task generation survives slow jobs, transient model failures and one bad mission."""

import time
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pack_translation import pack_shaped
from sqlalchemy import select, update
from test_background_jobs import DeferringRunner
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.ai.features.translation.schemas import SceneTranslationResult
from app.repositories.postgres import workflow
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.workflow import PostgresWorkflowRepository, _StaleGeneration
from app.repositories.practice import PracticeConflictError
from app.schemas.base import utc_now
from app.schemas.sessions import ReviewPracticeRequest


def translate(payload, cache_scope=None, **options):
    return SceneTranslationResult.model_validate(pack_shaped({
        kind: [{**term, "translation": "mesa"} for term in payload[kind]]
        for kind in ("objects", "attributes", "relationships")
    }, options))


def flaky(failures):
    """A translator that fails ``failures`` times before it translates."""
    calls = []

    def call(payload, cache_scope=None, **options):
        calls.append(payload)
        if len(calls) <= failures:
            raise RuntimeError("provider unavailable")
        return translate(payload, cache_scope, **options)

    return SimpleNamespace(translate=call), calls


def reviewed(database, repo):
    """A lesson session whose review was confirmed; its generation job is queued."""
    engine, owner, profile, client = database
    sid = UUID(create_run(client, profile, key=f"reliability-{uuid4()}")["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    repo.review(sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id]))
    return sid


def set_draft(engine, sid, **values):
    with engine.begin() as c:
        c.execute(
            update(sessions)
            .where(sessions.c.id == sid)
            .values(analysis_draft=sessions.c.analysis_draft.op("||")(values))
        )


@pytest.mark.usefixtures("regular_lesson")
def test_a_recent_heartbeat_keeps_a_long_generation_alive(database):
    engine, owner, profile, _ = database
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(engine, owner.id, background=runner)
    sid = reviewed(database, repo)
    long_ago = (utc_now() - timedelta(minutes=10)).isoformat()

    set_draft(engine, sid, processingStartedAt=long_ago, heartbeatAt=utc_now().isoformat())
    assert repo.get(sid, profile.id).session.status == "generatingTasks"

    set_draft(engine, sid, heartbeatAt=long_ago)
    session = repo.get(sid, profile.id).session
    assert session.status == "failed"
    assert session.failure_code == "taskGenerationFailed"


@pytest.mark.usefixtures("regular_lesson")
def test_a_running_job_refreshes_its_heartbeat(database, monkeypatch):
    engine, owner, profile, _ = database
    monkeypatch.setattr(workflow, "GENERATION_HEARTBEAT_SECONDS", 0.05)
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(engine, owner.id, background=runner)
    sid = reviewed(database, repo)
    seen = []

    def slow(_claim):
        time.sleep(0.5)
        with engine.connect() as c:
            seen.append(c.execute(
                select(sessions.c.analysis_draft).where(sessions.c.id == sid)
            ).scalar_one().get("heartbeatAt"))

    repo._run_task_generation(sid, profile.id, generate=slow)
    assert seen[0] is not None


@pytest.mark.usefixtures("regular_lesson")
def test_a_failed_translation_is_retried_once(database):
    engine, owner, profile, _ = database
    translator, calls = flaky(failures=1)
    repo = PostgresWorkflowRepository(
        engine, owner.id, background=DeferringRunner(), translator=translator,
        learning_task_generator=SimpleNamespace(generate=lambda *a, **k: 1 / 0),
    )
    sid = reviewed(database, repo)
    repo.background.jobs.pop()()
    assert len(calls) == 2
    assert repo.get(sid, profile.id).session.status == "inProgress"


@pytest.mark.usefixtures("regular_lesson")
def test_a_failed_lesson_build_can_be_retried_from_the_saved_review(database):
    engine, owner, profile, client = database
    translator, calls = flaky(failures=2)
    repo = PostgresWorkflowRepository(
        engine, owner.id, background=DeferringRunner(), translator=translator,
        learning_task_generator=SimpleNamespace(generate=lambda *a, **k: 1 / 0),
    )
    sid = reviewed(database, repo)
    repo.background.jobs.pop()()
    failed = repo.get(sid, profile.id)
    assert failed.session.status == "failed"
    assert failed.generation_retryable
    assert failed.analysis_retryable is False
    assert client.get(f"/api/v1/sessions/{sid}").json()["generationRetryable"] is True

    claimed = repo.retry_generation(sid, profile.id)
    assert claimed.session.status == "generatingTasks"
    assert claimed.session.failure_code is None
    assert claimed.session.analysis_draft["generationAttempts"] == 2
    # A second retry while the first is queued returns the claimed session.
    assert repo.retry_generation(sid, profile.id).session.status == "generatingTasks"
    assert len(repo.background.jobs) == 1

    repo.background.jobs.pop()()
    settled = repo.get(sid, profile.id)
    assert settled.session.status == "inProgress"
    assert settled.tasks
    assert len(calls) == 3


@pytest.mark.usefixtures("regular_lesson")
def test_lesson_build_retries_are_capped(database):
    engine, owner, profile, client = database
    translator, _ = flaky(failures=99)
    repo = PostgresWorkflowRepository(
        engine, owner.id, background=DeferringRunner(), translator=translator,
    )
    sid = reviewed(database, repo)
    repo.background.jobs.pop()()
    for _ in range(workflow.MAX_GENERATION_ATTEMPTS - 1):
        repo.retry_generation(sid, profile.id)
        repo.background.jobs.pop()()
    exhausted = repo.get(sid, profile.id)
    assert exhausted.session.status == "failed"
    assert not exhausted.generation_retryable
    with pytest.raises(PracticeConflictError):
        repo.retry_generation(sid, profile.id)
    assert client.post(f"/api/v1/sessions/{sid}/retry-generation").status_code == 409


def test_only_lesson_build_failures_can_retry_the_build(database):
    engine, _, profile, client = database
    sid = create_run(client, profile, key=f"reliability-{uuid4()}")["session"]["id"]
    with engine.begin() as c:
        c.execute(
            update(sessions)
            .where(sessions.c.id == UUID(sid))
            .values(status="failed", failure_code="sceneAnalysisFailed")
        )
    assert client.get(f"/api/v1/sessions/{sid}").json()["generationRetryable"] is False
    assert client.post(f"/api/v1/sessions/{sid}/retry-generation").status_code == 409


def mission_claim(*mission_ids):
    context = SimpleNamespace(
        owns=lambda _mission_id: True, display=SimpleNamespace(register_id="everyday")
    )
    return SimpleNamespace(
        session_id=uuid4(), revision=1, profile={"target_language_code": "es"},
        language_context=context,
        missions=tuple(
            SimpleNamespace(mission_id=mission_id, practice_level="A2")
            for mission_id in mission_ids
        ),
        roleplay_facts=None, learner_facts=None, mission_progress=None,
        review_markers=None, cache_scope=None, counted_groups=(),
    )


def mission_repo(monkeypatch, generate):
    monkeypatch.setattr(workflow, "lesson_mission", lambda planned: planned)
    repo = PostgresWorkflowRepository(
        None, uuid4(), learning_task_generator=SimpleNamespace(generate_pack_lesson=generate)
    )
    monkeypatch.setattr(repo, "_ensure_current", lambda claim: None)
    return repo


def test_one_failed_mission_is_skipped_and_the_rest_are_kept(monkeypatch):
    calls = []

    def generate(mission, *args, **kwargs):
        calls.append(mission.mission_id)
        if mission.mission_id == "M02":
            raise LearningTaskGenerationError("unusable output")
        return f"lesson-{mission.mission_id}"

    repo = mission_repo(monkeypatch, generate)
    skipped = []
    lessons = repo._mission_lessons(mission_claim("M01", "M02", "M03"), [], [], [], None, skipped)
    assert lessons == ["lesson-M01", "lesson-M03"]
    assert skipped == [{"missionId": "M02", "reason": "generationFailed"}]
    assert calls == ["M01", "M02", "M02", "M03"]


def test_a_mission_that_fails_once_is_kept(monkeypatch):
    calls = []

    def generate(mission, *args, **kwargs):
        calls.append(mission.mission_id)
        if len(calls) == 1:
            raise RuntimeError("provider timeout")
        return f"lesson-{mission.mission_id}"

    skipped = []
    lessons = mission_repo(monkeypatch, generate)._mission_lessons(
        mission_claim("M01"), [], [], [], None, skipped
    )
    assert lessons == ["lesson-M01"]
    assert skipped == []


def test_generation_fails_when_every_mission_fails(monkeypatch):
    def generate(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        mission_repo(monkeypatch, generate)._mission_lessons(
            mission_claim("M01", "M02"), [], [], [], None, []
        )


def test_a_moved_on_session_stops_instead_of_retrying(monkeypatch):
    calls = []

    def generate(mission, *args, **kwargs):
        calls.append(mission.mission_id)
        raise RuntimeError("provider unavailable")

    repo = mission_repo(monkeypatch, generate)

    def stale(claim):
        raise _StaleGeneration(str(claim.session_id))

    monkeypatch.setattr(repo, "_ensure_current", stale)
    with pytest.raises(_StaleGeneration):
        repo._mission_lessons(mission_claim("M01", "M02"), [], [], [], None, [])
    assert calls == ["M01"]
