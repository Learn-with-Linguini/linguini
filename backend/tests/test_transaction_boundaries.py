"""Provider calls run with no database transaction open; stale results are dropped."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import event, func, select, update
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.ai.features.ispy_clues import ISpyClueGenerationError
from app.ai.features.ispy_guess import ISpyGuessError, ISpyGuessResult
from app.ai.features.translation.schemas import SceneTranslationResult
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import (
    session_tasks,
    task_attempts,
    task_evaluation_claims,
)
from app.repositories.postgres.users import users
from app.repositories.postgres.workflow import (
    PostgresWorkflowRepository,
    _request_fingerprint,
)
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.sessions import ReviewPracticeRequest
from app.schemas.tasks import SubmitTextAttemptRequest

FALLBACK = "Your description was saved. Keep using scene words."


class NoTransactionProbe:
    """Fails a provider call made while this thread holds a SQLAlchemy transaction."""

    def __init__(self, engine, user_id):
        self.engine = engine
        self.user_id = user_id
        self.open = {}
        self.calls = 0
        # Concurrent provider calls must not trip over each other's lock checks.
        self._lock_check = threading.Lock()
        self.listeners = [
            ("begin", self._begin),
            ("commit", self._end),
            ("rollback", self._end),
        ]
        for name, listener in self.listeners:
            event.listen(engine.engine, name, listener)

    def _begin(self, connection):
        self.open[id(connection)] = threading.get_ident()

    def _end(self, connection):
        self.open.pop(id(connection), None)

    def check(self, *, lock=True):
        self.calls += 1
        assert threading.get_ident() not in self.open.values(), (
            "provider called inside an open SQLAlchemy transaction"
        )
        if lock:
            # Raises if any connection still holds the per-user row lock.
            with self._lock_check, self.engine.connect() as connection:
                connection.execute(
                    select(users.c.id)
                    .where(users.c.id == self.user_id)
                    .with_for_update(nowait=True)
                )

    def close(self):
        for name, listener in self.listeners:
            event.remove(self.engine.engine, name, listener)


class Guesser:
    def __init__(self, probe, *, lock=True):
        self.probe = probe
        self.lock = lock
        self.target_key = None
        self.error = None
        self.during = None
        self.calls = 0

    def guess(self, context, learner_text, *, session_id=None):
        self.probe.check(lock=self.lock)
        self.calls += 1
        if self.during:
            during, self.during = self.during, None
            during()
        if self.error:
            raise self.error
        return ISpyGuessResult(
            guessed_object_key=self.target_key,
            ambiguous=False,
            alternative_object_keys=[],
            matched_evidence_keys=[],
            contradicted_evidence_keys=[],
            feedback="Nice description.",
        )


class ManualRunner:
    """Holds the generation job so a test can start it once the session ID is known."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, /, *args, **kwargs):
        self.jobs.append(lambda: fn(*args, **kwargs))


@pytest.fixture
def probe(database):
    engine, owner, _profile, _client = database
    probe = NoTransactionProbe(engine, owner.id)
    yield probe
    probe.close()


def translate_with(probe, before=None):
    def translate(payload):
        probe.check()
        if before:
            before.pop()()
        return SceneTranslationResult.model_validate({
            kind: [
                {**term, "translation": "mesa", "phoneticText": "MEH-sah"}
                for term in payload[kind]
            ]
            for kind in ("objects", "attributes", "relationships")
        })

    return SimpleNamespace(translate=translate)


def generate_with(probe, error, before=None):
    def generate(_payload):
        probe.check()
        if before:
            before.pop()()
        raise error

    return SimpleNamespace(generate=generate)


def build_repo(database, probe, **overrides):
    engine, owner, _profile, _client = database
    providers = {
        "translator": translate_with(probe),
        "learning_task_generator": generate_with(probe, ValueError("deterministic")),
        "ispy_clue_generator": generate_with(probe, ISpyClueGenerationError("off")),
        "ispy_guess_generator": Guesser(probe),
    } | overrides
    return PostgresWorkflowRepository(engine, owner.id, **providers)


def start(database, repo):
    _engine, _owner, profile, client = database
    sid = UUID(create_run(client, profile)["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    repo.review(sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id]))
    return sid


def scalar(engine, statement):
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one()


def description_task(engine, sid):
    with engine.connect() as connection:
        rows = connection.execute(
            select(session_tasks).where(
                session_tasks.c.session_id == sid, session_tasks.c.kind == "reflection"
            )
        ).mappings()
        return next(row for row in rows if (row["answer_key"] or {}).get(
            "sceneDescriptionContext"
        ))


def described_session(database, probe, *, lock=True):
    engine = database[0]
    guesser = Guesser(probe, lock=lock)
    repo = build_repo(database, probe, ispy_guess_generator=guesser)
    sid = start(database, repo)
    task = description_task(engine, sid)
    guesser.target_key = str(task["scene_object_id"])
    return repo, sid, task["id"], guesser


def describe(key):
    return SubmitTextAttemptRequest(text="Es una mesa marrón.", idempotency_key=key)


def attempt_count(engine, task_id):
    return scalar(
        engine,
        select(func.count()).select_from(task_attempts).where(
            task_attempts.c.session_task_id == task_id
        ),
    )


def ispy_xp_count(engine, sid):
    return scalar(
        engine,
        select(func.count()).select_from(xp_events).where(
            xp_events.c.session_id == sid, xp_events.c.event_type == "ispyCorrect"
        ),
    )


def claim_of(engine, task_id):
    return scalar(
        engine,
        select(task_evaluation_claims.c.evaluation_claim_id).where(
            task_evaluation_claims.c.id == task_id
        ),
    )


def test_probe_rejects_a_call_inside_a_transaction(database, probe):
    engine, owner, profile, client = database
    with engine.begin(), pytest.raises(AssertionError, match="open SQLAlchemy transaction"):
        probe.check()


def test_generation_providers_run_without_a_transaction(database, probe):
    engine = database[0]
    repo = build_repo(database, probe)
    sid = start(database, repo)
    # Translation, lesson generation and clue generation.
    assert probe.calls == 3
    detail = repo.get(sid, database[2].id)
    assert detail.session.status == "inProgress"
    assert [task.order_index for task in detail.tasks] == list(range(len(detail.tasks)))
    assert detail.tasks[0].kind == "vocabularyIntroduction"
    assert description_task(engine, sid)
    assert scalar(
        engine, select(sessions.c.generation_revision).where(sessions.c.id == sid)
    ) == 1


def test_stale_translation_is_discarded_for_the_newer_generation(database, probe):
    engine, _owner, profile, _client = database
    newer = []
    runner = ManualRunner()
    repo = build_repo(
        database, probe, translator=translate_with(probe, before=newer), background=runner
    )
    sid = start(database, repo)
    newer.append(lambda: repo._run_task_generation(sid, profile.id))
    runner.jobs.pop()()
    detail = repo.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    assert scalar(
        engine, select(sessions.c.generation_revision).where(sessions.c.id == sid)
    ) == 2
    kinds = [task.kind for task in detail.tasks]
    assert kinds.count("vocabularyIntroduction") == 1
    assert [task.order_index for task in detail.tasks] == list(range(len(detail.tasks)))


def test_stale_lessons_do_not_overwrite_the_newer_plan(database, probe):
    _engine, _owner, profile, _client = database
    newer = []
    runner = ManualRunner()
    repo = build_repo(
        database,
        probe,
        learning_task_generator=generate_with(probe, ValueError("deterministic"), newer),
        background=runner,
    )
    sid = start(database, repo)
    newer.append(lambda: repo._run_task_generation(sid, profile.id))
    runner.jobs.pop()()
    detail = repo.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    ids = [task.id for task in detail.tasks]
    assert len(ids) == len(set(ids))
    assert [task.order_index for task in detail.tasks] == list(range(len(detail.tasks)))


def test_stale_generation_failure_does_not_fail_the_newer_generation(database, probe):
    _engine, _owner, profile, _client = database
    newer = []

    def translate(payload):
        if newer:
            newer.pop()()
            raise RuntimeError("provider timed out after a newer claim")
        return translate_with(probe).translate(payload)

    runner = ManualRunner()
    repo = build_repo(
        database, probe, translator=SimpleNamespace(translate=translate), background=runner
    )
    sid = start(database, repo)
    newer.append(lambda: repo._run_task_generation(sid, profile.id))
    runner.jobs.pop()()
    session = repo.get(sid, profile.id).session
    assert session.status == "inProgress"
    assert session.failure_code is None


def test_current_generation_failure_still_fails_the_session(database, probe):
    def translate(_payload):
        probe.check()
        raise RuntimeError("provider unavailable")

    repo = build_repo(database, probe, translator=SimpleNamespace(translate=translate))
    sid = start(database, repo)
    session = repo.get(sid, database[2].id).session
    assert session.status == "failed"
    assert session.failure_code == "taskGenerationFailed"


def test_ispy_evaluation_runs_without_a_transaction_and_retries_idempotently(
    database, probe
):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)
    first = repo.task_action(task_id, "attempt", describe("describe-once-1"))
    assert first.attempt.is_correct is True
    assert guesser.calls == 1
    assert claim_of(engine, task_id) is None
    retry = repo.task_action(task_id, "attempt", describe("describe-once-1"))
    assert retry.attempt.id == first.attempt.id
    assert guesser.calls == 1
    assert attempt_count(engine, task_id) == 1
    assert ispy_xp_count(engine, sid) == 1


def test_concurrent_retries_share_one_evaluation_and_award_once(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe, lock=False)
    entered = threading.Barrier(4, timeout=10)
    original = guesser.guess

    def slow_guess(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    def attempt(_):
        entered.wait()
        return repo.task_action(task_id, "attempt", describe("describe-race-1"))

    guesser.guess = slow_guess
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(attempt, range(4)))
    assert guesser.calls == 1
    assert len({response.attempt.id for response in responses}) == 1
    assert attempt_count(engine, task_id) == 1
    assert ispy_xp_count(engine, sid) == 1
    assert claim_of(engine, task_id) is None


def test_duplicate_waits_for_the_lease_holder_instead_of_calling_the_model(
    database, probe
):
    repo, _sid, task_id, guesser = described_session(database, probe)
    waiting = threading.Event()
    original_wait = repo._await_evaluation

    def await_evaluation(pending):
        waiting.set()
        return original_wait(pending)

    repo._await_evaluation = await_evaluation
    duplicates = []
    duplicate = threading.Thread(target=lambda: duplicates.append(
        repo.task_action(task_id, "attempt", describe("describe-wait-1"))
    ))

    def start_duplicate():
        duplicate.start()
        assert waiting.wait(10)

    guesser.during = start_duplicate
    first = repo.task_action(task_id, "attempt", describe("describe-wait-1"))
    duplicate.join(10)
    assert guesser.calls == 1
    assert duplicates[0].attempt.id == first.attempt.id


def test_key_reuse_with_different_input_is_rejected_before_the_model(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)
    other = SubmitTextAttemptRequest(text="Es una silla.", idempotency_key="describe-reuse-1")
    rejected = []

    def reuse_key():
        with pytest.raises(PracticeConflictError, match="another answer"):
            repo.task_action(task_id, "attempt", other)
        rejected.append(True)

    guesser.during = reuse_key
    saved = repo.task_action(task_id, "attempt", describe("describe-reuse-1"))
    assert rejected and saved.attempt.is_correct is True
    with pytest.raises(PracticeConflictError, match="another answer"):
        repo.task_action(task_id, "attempt", other)
    assert guesser.calls == 1
    assert attempt_count(engine, task_id) == 1
    assert ispy_xp_count(engine, sid) == 1


def abandon_claim(engine, task_id, key, expires_in):
    with engine.begin() as connection:
        connection.execute(
            update(task_evaluation_claims)
            .where(task_evaluation_claims.c.id == task_id)
            .values(
                evaluation_claim_id=uuid5(task_id, "attempt:" + key),
                evaluation_claim_fingerprint=_request_fingerprint(describe(key)),
                evaluation_claim_expires_at=func.now() + timedelta(seconds=expires_in),
            )
        )


def test_expired_abandoned_claim_is_taken_over(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)
    abandon_claim(engine, task_id, "describe-crash-1", expires_in=-1)
    response = repo.task_action(task_id, "attempt", describe("describe-crash-1"))
    assert response.attempt.is_correct is True
    assert guesser.calls == 1
    assert claim_of(engine, task_id) is None
    assert ispy_xp_count(engine, sid) == 1


def test_live_abandoned_claim_is_recovered_when_its_lease_expires(database, probe):
    engine = database[0]
    repo, _sid, task_id, guesser = described_session(database, probe)
    abandon_claim(engine, task_id, "describe-crash-2", expires_in=0.5)
    started = time.monotonic()
    response = repo.task_action(task_id, "attempt", describe("describe-crash-2"))
    assert time.monotonic() - started >= 0.4
    assert response.attempt.is_correct is True
    assert guesser.calls == 1


def test_unexpected_failure_releases_the_claim_for_a_retry(database, probe):
    engine = database[0]
    repo, _sid, task_id, guesser = described_session(database, probe)
    guesser.error = RuntimeError("worker crashed")
    with pytest.raises(RuntimeError):
        repo.task_action(task_id, "attempt", describe("describe-boom-1"))
    assert claim_of(engine, task_id) is None
    guesser.error = None
    response = repo.task_action(task_id, "attempt", describe("describe-boom-1"))
    assert response.attempt.is_correct is True
    assert guesser.calls == 2


def test_replaced_claim_is_rejected_then_retry_succeeds(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)

    def newer_claim():
        with engine.begin() as connection:
            connection.execute(
                update(task_evaluation_claims)
                .where(task_evaluation_claims.c.id == task_id)
                .values(evaluation_claim_id=uuid4())
            )

    guesser.during = newer_claim
    with pytest.raises(PracticeConflictError):
        repo.task_action(task_id, "attempt", describe("describe-stale-1"))
    assert attempt_count(engine, task_id) == 0
    assert ispy_xp_count(engine, sid) == 0
    retried = repo.task_action(task_id, "attempt", describe("describe-stale-1"))
    assert retried.attempt.is_correct is True
    assert attempt_count(engine, task_id) == 1
    assert ispy_xp_count(engine, sid) == 1


def test_attempt_finished_during_evaluation_rejects_the_stale_one(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)
    saved = []
    guesser.during = lambda: saved.append(
        repo.task_action(task_id, "attempt", describe("describe-newer-1"))
    )
    with pytest.raises(PracticeConflictError):
        repo.task_action(task_id, "attempt", describe("describe-older-1"))
    assert saved[0].attempt.is_correct is True
    assert attempt_count(engine, task_id) == 1
    assert ispy_xp_count(engine, sid) == 1


def test_provider_failure_saves_the_ungraded_fallback(database, probe):
    engine = database[0]
    repo, sid, task_id, guesser = described_session(database, probe)
    guesser.error = ISpyGuessError("provider unavailable")
    response = repo.task_action(task_id, "attempt", describe("describe-down-1"))
    assert guesser.calls == 1
    assert response.attempt.is_correct is None
    assert FALLBACK in response.attempt.feedback.values()
    assert ispy_xp_count(engine, sid) == 0
    assert claim_of(engine, task_id) is None
    retry = repo.task_action(task_id, "attempt", describe("describe-down-1"))
    assert retry.attempt.id == response.attempt.id
    assert guesser.calls == 1
