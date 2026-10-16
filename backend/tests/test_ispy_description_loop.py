"""Round-two I-Spy: interpret each guess, revise clues and confirm the latest clear match."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from test_postgres_sessions import database as database
from test_transaction_boundaries import (
    attempt_count,
    described_session,
    ispy_xp_count,
    scalar,
)
from test_transaction_boundaries import probe as probe

from app.ai.features.ispy_guess import ISpyGuessError, ISpyGuessResult
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import user_vocabulary_progress
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import (
    ClueNamesTargetError,
    PracticeConflictError,
    PracticeNotFoundError,
)
from app.schemas.tasks import (
    ClueAssistance,
    ReflectionContent,
    SkipTaskRequest,
    SubmitTextAttemptRequest,
)
from app.schemas.users import User
from app.services.ispy_descriptions import (
    EVALUATION_FAILED_MESSAGE,
    OUTCOME_CORRECTNESS,
    interpret_guess,
)


def result(guessed=None, *, ambiguous=False, alternatives=(), contradicted=()):
    return ISpyGuessResult(
        guessed_object_key=guessed,
        ambiguous=ambiguous,
        alternative_object_keys=list(alternatives),
        matched_evidence_keys=[],
        contradicted_evidence_keys=list(contradicted),
        feedback="Model feedback.",
    )


@pytest.fixture
def loop(database, probe):
    repo, sid, task_id, guesser = described_session(database, probe)
    target = guesser.target_key
    # The repository trusts schema-validated keys; any non-target key is a miss.
    other = str(uuid4())
    replies = []
    original = guesser.guess

    def guess(*args, **kwargs):
        original(*args, **kwargs)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    guesser.guess = guess
    return repo, sid, task_id, guesser, target, other, replies


def submit(repo, task_id, key, text="Es marrón y está a la izquierda."):
    return repo.task_action(
        task_id, "attempt", SubmitTextAttemptRequest(text=text, idempotency_key=f"loop-{key}")
    )


def xp_events_of(engine, sid, event_type):
    return scalar(
        engine,
        select(func.count()).select_from(xp_events).where(
            xp_events.c.session_id == sid, xp_events.c.event_type == event_type
        ),
    )


def correct_attempts(engine, owner_id):
    return scalar(
        engine,
        select(func.coalesce(func.sum(user_vocabulary_progress.c.correct_attempt_count), 0)).where(
            user_vocabulary_progress.c.user_id == owner_id
        ),
    )


def summary(repo, engine, sid):
    with engine.connect() as c:
        return repo._ispy_summary(c, sid)


@pytest.mark.parametrize(
    ("kwargs", "outcome", "correct"),
    [
        (dict(guessed="target"), "clearMatch", True),
        (dict(guessed="target", ambiguous=True), "clearMatch", True),
        (
            dict(guessed="other", ambiguous=True, alternatives=["target"]),
            "needsClarification",
            None,
        ),
        (dict(guessed="target", contradicted=["colour:red"]), "needsRevision", None),
        (dict(guessed="other"), "noMatch", False),
        (dict(guessed=None), "noMatch", False),
    ],
)
def test_interpretation_requires_an_unambiguous_uncontradicted_target(kwargs, outcome, correct):
    target = UUID(int=1)
    names = {"target": str(target), "other": str(UUID(int=2))}
    kwargs = {
        key: names.get(value, value)
        if not isinstance(value, list)
        else [names.get(item, item) for item in value]
        for key, value in kwargs.items()
    }
    interpretation = interpret_guess(result(**kwargs), target)
    assert interpretation.outcome == outcome
    assert interpretation.version == "ispy-description-evaluation.v1"
    assert OUTCOME_CORRECTNESS[outcome] is correct


def test_interpretation_ignores_other_object_contradictions_but_keeps_all_evidence():
    target_id = UUID(int=1)
    target, other = str(target_id), str(UUID(int=2))
    contradicted = ["other:color", "target:color", "target:relation"]
    context = {
        "sceneObjects": {
            "attributes": [
                {"key": "other:color", "objectKey": other},
                {"key": "target:color"},
            ],
            "relations": [
                {
                    "key": "target:relation",
                    "subjectObjectKey": target,
                    "referenceObjectKey": other,
                }
            ],
        }
    }

    other_only = interpret_guess(
        result(target, ambiguous=True, contradicted=["other:color"]), target_id, context
    )
    assert other_only.outcome == "clearMatch"
    assert OUTCOME_CORRECTNESS[other_only.outcome] is True
    assert other_only.contradicted_evidence_keys == ["other:color"]

    target_evidence = interpret_guess(result(target, contradicted=contradicted), target_id, context)
    assert target_evidence.outcome == "needsRevision"
    assert target_evidence.contradicted_evidence_keys == contradicted


def test_english_clue_error_returns_the_target_language_api_error(database, loop):
    _engine, _owner, _profile, client = database
    _repo, _sid, task_id, _guesser, _target, _other, _replies = loop

    response = client.post(
        f"/api/v1/tasks/{task_id}/attempts",
        json={
            "inputMode": "text",
            "text": "It is red",
            "idempotencyKey": "english-clue-api",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "clue_not_target_language"
    assert response.json()["detail"]["message"] == (
        "Write your clue in your learning language, not English."
    )
    assert attempt_count(_engine, task_id) == 0


def test_clear_match_waits_for_confirmation_then_rewards_once(database, loop):
    engine, owner = database[0], database[1]
    repo, sid, task_id, _guesser, target, _other, replies = loop
    replies.append(result(target))
    saved = submit(repo, task_id, "clear-1")
    details = saved.attempt.evaluation_details
    assert details["version"] == "ispy-description-evaluation.v1"
    assert details["outcome"] == "clearMatch"
    assert details["guessedObjectKey"] == target
    assert saved.task.status == "inProgress"
    assert saved.attempt.attempt_number == 1
    assert ispy_xp_count(engine, sid) == 0
    assert xp_events_of(engine, sid, "taskCompleted") == 0
    assert summary(repo, engine, sid) == {"ispy_correct_count": 0, "ispy_attempt_count": 1}

    confirmed = repo.confirm_guess(task_id, saved.attempt.id)
    assert confirmed.task.status == "completed"
    assert confirmed.attempt.id == saved.attempt.id
    again = repo.confirm_guess(task_id, saved.attempt.id)
    assert again.task.status == "completed"
    assert ispy_xp_count(engine, sid) == 1
    assert xp_events_of(engine, sid, "taskCompleted") == 1
    assert summary(repo, engine, sid) == {"ispy_correct_count": 1, "ispy_attempt_count": 1}
    # The model naming the object is not evidence the learner produced the noun.
    assert correct_attempts(engine, owner.id) == 0


@pytest.mark.parametrize(
    ("reply", "outcome", "correct"),
    [
        (lambda t, o: result(o, ambiguous=True, alternatives=[t]), "needsClarification", None),
        (lambda t, o: result(t, contradicted=["colour:red"]), "needsRevision", None),
        (lambda t, o: result(o), "noMatch", False),
        (lambda t, o: result(None), "noMatch", False),
    ],
)
def test_unresolved_outcomes_stay_active_and_cannot_be_confirmed(
    database, loop, reply, outcome, correct
):
    engine = database[0]
    repo, sid, task_id, _guesser, target, other, replies = loop
    if outcome == "needsRevision":
        context = scalar(
            engine,
            select(session_tasks.c.answer_key).where(session_tasks.c.id == task_id),
        )["sceneDescriptionContext"]
        scene_objects = context["sceneObjects"]
        target_evidence = next(
            row["key"]
            for row in [*scene_objects["attributes"], *scene_objects["relations"]]
            if (
                row.get("objectKey") == target
                or row.get("subjectObjectKey") == target
                or row.get("referenceObjectKey") == target
                or row.get("key", "").rsplit(":", 1)[0] == target
            )
        )
        replies.append(result(target, contradicted=[target_evidence]))
    else:
        replies.append(reply(target, other))
    saved = submit(repo, task_id, "unresolved-1")
    assert saved.attempt.evaluation_details["outcome"] == outcome
    assert saved.attempt.is_correct is correct
    assert saved.task.status == "inProgress"
    if outcome == "needsClarification":
        assert saved.attempt.evaluation_details["targetAmongAlternatives"] is True
    with pytest.raises(PracticeConflictError, match="clear match"):
        repo.confirm_guess(task_id, saved.attempt.id)
    assert ispy_xp_count(engine, sid) == 0
    assert xp_events_of(engine, sid, "taskCompleted") == 0
    assert summary(repo, engine, sid)["ispy_correct_count"] == 0


def test_provider_failure_keeps_the_clue_and_allows_a_new_key(database, loop):
    engine = database[0]
    repo, sid, task_id, guesser, target, _other, replies = loop
    replies += [ISpyGuessError("provider unavailable"), result(target)]
    failed = submit(repo, task_id, "down-1")
    assert failed.attempt.evaluation_details["outcome"] == "evaluationFailed"
    assert failed.attempt.feedback == {"message": EVALUATION_FAILED_MESSAGE}
    assert failed.attempt.response_payload["text"] == "Es marrón y está a la izquierda."
    assert failed.attempt.is_correct is None
    assert failed.task.status == "inProgress"
    with pytest.raises(PracticeConflictError):
        repo.confirm_guess(task_id, failed.attempt.id)
    assert summary(repo, engine, sid) == {"ispy_correct_count": 0, "ispy_attempt_count": 1}

    retried = submit(repo, task_id, "down-2")
    assert retried.attempt.attempt_number == 2
    assert retried.attempt.evaluation_details["outcome"] == "clearMatch"
    assert guesser.calls == 2
    assert ispy_xp_count(engine, sid) == 0


def test_revision_allocates_attempt_numbers_and_rejects_stale_confirmation(database, loop):
    engine = database[0]
    repo, sid, task_id, _guesser, target, other, replies = loop
    replies += [result(target), result(other), result(target)]
    first = submit(repo, task_id, "revise-1")
    second = submit(repo, task_id, "revise-2", "Es roja.")
    assert [first.attempt.attempt_number, second.attempt.attempt_number] == [1, 2]
    with pytest.raises(PracticeConflictError, match="latest"):
        repo.confirm_guess(task_id, first.attempt.id)
    third = submit(repo, task_id, "revise-3", "Es grande y marrón.")
    assert third.attempt.attempt_number == 3
    with pytest.raises(PracticeConflictError, match="latest"):
        repo.confirm_guess(task_id, first.attempt.id)
    assert repo.confirm_guess(task_id, third.attempt.id).task.status == "completed"
    assert attempt_count(engine, task_id) == 3
    assert ispy_xp_count(engine, sid) == 1
    assert summary(repo, engine, sid) == {"ispy_correct_count": 1, "ispy_attempt_count": 1}
    with pytest.raises(PracticeConflictError, match="not active"):
        submit(repo, task_id, "revise-4")


def test_duplicate_submission_returns_the_saved_attempt(database, loop):
    engine = database[0]
    repo, _sid, task_id, guesser, target, _other, replies = loop
    replies.append(result(target))
    first = submit(repo, task_id, "dup-1")
    retry = submit(repo, task_id, "dup-1")
    assert retry.attempt == first.attempt
    assert guesser.calls == 1
    assert attempt_count(engine, task_id) == 1


def test_skip_after_unresolved_guess_awards_nothing(database, loop):
    engine = database[0]
    repo, sid, task_id, _guesser, target, _other, replies = loop
    replies.append(result(target, ambiguous=True))
    saved = submit(repo, task_id, "skip-1")
    skipped = repo.task_action(task_id, "skip", SkipTaskRequest(reason="tooHard"))
    assert skipped.task.status == "skipped"
    with pytest.raises(PracticeConflictError):
        repo.confirm_guess(task_id, saved.attempt.id)
    assert ispy_xp_count(engine, sid) == 0
    assert xp_events_of(engine, sid, "taskCompleted") == 0
    assert summary(repo, engine, sid) == {"ispy_correct_count": 0, "ispy_attempt_count": 1}


def test_confirmation_is_owner_scoped_and_description_only(database, loop):
    engine = database[0]
    repo, sid, task_id, _guesser, target, _other, replies = loop
    replies.append(result(target))
    saved = submit(repo, task_id, "owner-1")
    stranger = User(display_name="Other learner", auth_provider_id=f"stranger-{uuid4()}")
    with engine.begin() as c:
        c.execute(insert(users).values(**stranger.model_dump(by_alias=False)))
    try:
        with pytest.raises(PracticeNotFoundError):
            PostgresWorkflowRepository(engine, stranger.id).confirm_guess(
                task_id, saved.attempt.id
            )
    finally:
        with engine.begin() as c:
            c.execute(delete(users).where(users.c.id == stranger.id))
    with engine.connect() as c:
        other_task = c.execute(
            select(session_tasks.c.id).where(
                session_tasks.c.session_id == sid, session_tasks.c.kind != "reflection"
            )
        ).scalars().first()
    with pytest.raises(PracticeConflictError, match="I-Spy descriptions"):
        repo.confirm_guess(other_task, saved.attempt.id)


def described_content(engine, task_id):
    with engine.connect() as connection:
        row = connection.execute(
            select(session_tasks.c.public_content).where(session_tasks.c.id == task_id)
        ).scalar_one()
    return ReflectionContent.model_validate(row)


def guided(content, text, key, **assistance):
    return SubmitTextAttemptRequest(
        text=text,
        idempotency_key=f"loop-{key}",
        assistance=ClueAssistance(
            offered_frame_ids=[frame.frame_id for frame in content.clue_frames], **assistance
        ),
    )


def test_described_tasks_publish_frames_and_target_words_outside_the_model_context(
    database, loop
):
    repo, _sid, task_id, guesser, target, _other, replies = loop
    content = described_content(database[0], task_id)
    seen = []
    wrapped = guesser.guess

    def record(context, learner_text, **kwargs):
        seen.append((context, learner_text))
        return wrapped(context, learner_text, **kwargs)

    guesser.guess = record
    replies.append(result(target))

    assert [frame.frame_id for frame in content.clue_frames] == ["colour"]
    assert content.clue_frames[0].help == ["azul"]
    assert "azul" in [chip.text for chip in content.clue_frames[0].slots[0].chips]
    assert content.avoid_words
    clue = "Veo algo. Es marrón y está a la izquierda."
    submit(repo, task_id, "complete", clue)

    context, learner_text = seen[0]
    assert learner_text == clue
    assert target not in str(context.get("selectedTargetObjectKey", ""))
    assert "avoidWords" not in str(context) and "clueFrames" not in str(context)


def test_a_clue_naming_the_target_is_rejected_before_any_model_call(database, loop):
    repo, _sid, task_id, guesser, _target, _other, _replies = loop
    word = described_content(database[0], task_id).avoid_words[0]

    with pytest.raises(ClueNamesTargetError):
        submit(repo, task_id, "names-target", f"Veo una {word.upper()} grande.")

    assert guesser.calls == 0
    assert attempt_count(database[0], task_id) == 0


def test_guided_support_is_recorded_per_attempt_and_restored_on_retry(database, loop):
    repo, _sid, task_id, _guesser, target, other, replies = loop
    engine = database[0]
    content = described_content(engine, task_id)
    colour = content.clue_frames[0]
    replies.extend([result(other), result(target)])

    first = repo.task_action(
        task_id, "attempt", guided(content, "Es azul.", "guided-1",
                                   selected_frame_ids=[colour.frame_id], inserted_chips=["azul"]),
    )
    restored = ClueAssistance.model_validate(first.attempt.response_payload["assistance"])
    assert restored.selected_frame_ids == ["colour"]
    assert restored.practice_mode == "guided" and restored.target_word_shown is True
    assert first.attempt.response_payload["text"] == "Es azul."

    retry = repo.task_action(
        task_id, "attempt", guided(content, "Es azul.", "guided-1",
                                   selected_frame_ids=[colour.frame_id], inserted_chips=["azul"]),
    )
    assert retry.attempt.id == first.attempt.id

    revised = submit(repo, task_id, "guided-2", "Es marrón y está a la izquierda.")
    assert "assistance" not in revised.attempt.response_payload
    assert revised.attempt.attempt_number == 2
    with pytest.raises(PracticeConflictError):
        repo.task_action(
            task_id, "attempt", guided(content, "Es roja.", "guided-3",
                                       selected_frame_ids=[colour.frame_id],
                                       inserted_chips=["not offered"]),
        )
    assert correct_attempts(engine, database[1].id) == 0


LATEST_FIELDS = {
    "id", "attemptNumber", "text", "optionId", "isCorrect", "feedback", "evaluationDetails",
    "assistance",
}


def latest(client, task_id):
    response = client.get(f"/api/v1/tasks/{task_id}/latest-attempt")
    assert response.status_code == 200, response.text
    return response.json()["attempt"]


def test_latest_attempt_restores_a_pending_clear_match_then_confirms_it(database, loop):
    engine, _owner, _profile, client = database
    repo, _sid, task_id, _guesser, target, other, replies = loop
    content = described_content(engine, task_id)
    assert latest(client, task_id) is None

    replies.extend([result(other), result(target)])
    submit(repo, task_id, "restore-1")
    saved = repo.task_action(
        task_id, "attempt", guided(content, "Es azul.", "restore-2",
                                   selected_frame_ids=["colour"], inserted_chips=["azul"]),
    )

    restored = latest(client, task_id)
    assert set(restored) == LATEST_FIELDS
    assert restored["id"] == str(saved.attempt.id) and restored["attemptNumber"] == 2
    assert restored["text"] == "Es azul."
    assert restored["evaluationDetails"]["outcome"] == "clearMatch"
    assert restored["evaluationDetails"]["guessedObjectKey"] == target
    assert restored["assistance"]["selectedFrameIds"] == ["colour"]
    assert restored["assistance"]["insertedChips"] == ["azul"]
    assert "sceneDescriptionContext" not in str(restored) and "answerKey" not in str(restored)

    confirmed = repo.confirm_guess(task_id, UUID(restored["id"]))
    assert confirmed.task.status == "completed"
    assert latest(client, task_id)["id"] == restored["id"]


def test_latest_attempt_restores_failed_and_skipped_tasks(database, loop):
    client = database[3]
    repo, _sid, task_id, _guesser, _target, _other, replies = loop
    replies.append(ISpyGuessError("provider down"))
    submit(repo, task_id, "restore-failed")

    failed = latest(client, task_id)
    assert failed["evaluationDetails"]["outcome"] == "evaluationFailed"
    assert failed["text"] == "Es marrón y está a la izquierda."

    repo.task_action(task_id, "skip", SkipTaskRequest())
    assert latest(client, task_id)["id"] == failed["id"]


def test_latest_attempt_is_owner_scoped_and_description_only(database, loop):
    from types import SimpleNamespace

    from app.repositories.postgres.tasks import PostgresTaskRepository
    from app.repositories.tasks import TaskNotFoundError
    from app.services.tasks import TaskService

    engine = database[0]
    repo, sid, task_id, _guesser, target, _other, replies = loop
    replies.append(result(target))
    submit(repo, task_id, "scoped-1")
    stranger = SimpleNamespace(id=uuid4())
    service = TaskService(
        PostgresTaskRepository(engine), SimpleNamespace(get_current_user=lambda: stranger)
    )
    with pytest.raises(TaskNotFoundError):
        service.latest_attempt(task_id)

    with engine.connect() as c:
        other_task = c.execute(
            select(session_tasks.c.id).where(
                session_tasks.c.session_id == sid, session_tasks.c.kind != "reflection"
            )
        ).scalars().first()
    assert latest(database[3], other_task) is None
