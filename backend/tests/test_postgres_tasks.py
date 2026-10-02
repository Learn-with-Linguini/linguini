from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import PostgresSceneObjectRepository
from app.repositories.postgres.tasks import (
    PostgresTaskRepository,
    entity_values,
    session_tasks,
    task_attempts,
    task_hints,
)
from app.repositories.tasks import TaskConflictError, TaskNotFoundError, TaskStorageError
from app.schemas.media import MediaAsset, SceneObject
from app.schemas.tasks import SessionTask, TaskAttempt, TaskHint


@pytest.fixture
def context(database):
    engine, owner, profile, client = database
    run = create_run(client, profile)["session"]
    task = SessionTask(
        session_id=run["id"],
        phase="learning",
        kind="grammarPractice",
        order_index=0,
        public_content={
            "kind": "grammarPractice",
            "prompt": "Choose a word",
            "options": ["uno", "dos"],
        },
        answer_key={"acceptedTextAnswers": ["secret-answer"], "evaluationNotes": "private-note"},
    )
    repository = PostgresTaskRepository(engine)
    yield engine, owner, client, repository, task, run
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.user_id == owner.id))
        connection.execute(delete(media_assets).where(media_assets.c.owner_user_id == owner.id))


def test_roundtrip_public_reads_and_order(context):
    engine, owner, client, repository, task, run = context
    repository.create_task(task.model_copy(update={"id": uuid4(), "order_index": 2}), owner.id)
    saved = repository.create_task(task, owner.id)
    assert saved.answer_key.evaluation_notes == "private-note"
    assert repository.create_task(task, owner.id).id == task.id
    for endpoint in [
        f"/api/v1/tasks/{task.id}",
        f"/api/v1/sessions/{task.session_id}",
        f"/api/v1/sessions/{task.session_id}/tasks",
    ]:
        response = client.get(endpoint)
        assert response.status_code == 200, response.text
        assert "answerKey" not in response.text
        assert "secret-answer" not in response.text
        assert "private-note" not in response.text
    detail = client.get(f"/api/v1/sessions/{task.session_id}").json()
    assert [row["orderIndex"] for row in detail["tasks"]] == [0, 2]
    assert detail["nextTaskId"] == str(task.id)
    assert detail["progress"]["totalTaskCount"] == 2
    assert repository.get(task.id, uuid4()) is None
    assert repository.list_for_session(task.session_id, uuid4()) == []
    assert client.get(f"/api/v1/tasks/{uuid4()}").status_code == 404
    with pytest.raises(TaskNotFoundError):
        repository.create_task(task, uuid4())


def test_attempts_hints_roundtrip_and_retry(context):
    engine, owner, client, repository, task, run = context
    repository.create_task(task, owner.id)
    attempt = TaskAttempt(
        session_task_id=task.id,
        attempt_number=1,
        input_mode="text",
        response_payload={"text": "uno"},
        is_correct=False,
        score=Decimal("0.123456"),
        feedback={"message": "Try again"},
        evaluation_details={"rule": "internal"},
    )
    hint = TaskHint(session_task_id=task.id, hint_level=1, content={"text": "Look at the article"})
    assert repository.create_attempt(attempt, owner.id).score == Decimal("0.12346")
    assert repository.create_attempt(attempt, owner.id).id == attempt.id
    assert repository.create_hint(hint, owner.id).id == hint.id
    assert repository.create_hint(hint, owner.id).id == hint.id
    assert repository.list_attempts(task.id, owner.id)[0].feedback == attempt.feedback
    assert repository.list_hints(task.id, owner.id)[0].content == hint.content
    assert repository.list_attempts(task.id, uuid4()) == []
    assert repository.list_hints(task.id, uuid4()) == []
    with pytest.raises(TaskConflictError):
        repository.create_attempt(attempt.model_copy(update={"id": uuid4()}), owner.id)
    with pytest.raises(TaskConflictError):
        repository.create_hint(hint.model_copy(update={"id": uuid4()}), owner.id)
    # A pending evaluation remains SQL NULL rather than JSON null.
    pending = TaskAttempt(
        session_task_id=task.id, attempt_number=2, input_mode="text", response_payload={}
    )
    assert repository.create_attempt(pending, owner.id).is_correct is None


def test_concurrent_position_conflicts_do_not_overwrite(context):
    _, owner, _, repository, task, _ = context

    def create(_):
        try:
            repository.create_task(task.model_copy(update={"id": uuid4()}), owner.id)
            return "saved"
        except TaskConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as workers:
        outcomes = list(workers.map(create, range(4)))
    assert outcomes.count("saved") == 1
    assert outcomes.count("conflict") == 3


def test_wrong_session_object_and_owned_audio_constraints(context):
    engine, owner, client, repository, task, run = context
    item = SceneObject(
        session_id=run["id"],
        label="cup",
        bounding_box={"x": 0, "y": 0, "width": 1, "height": 1},
    )
    PostgresSceneObjectRepository(engine).create(item)
    task.scene_object_id = item.id
    repository.create_task(task, owner.id)
    audio = MediaAsset(
        owner_user_id=owner.id,
        media_type="audio",
        source="userUpload",
        storage_key=f"test-audio/{uuid4()}",
        mime_type="audio/wav",
    )
    shared = MediaAsset(
        media_type="audio",
        source="preloaded",
        storage_key=f"test-audio/{uuid4()}",
        mime_type="audio/wav",
    )
    with engine.begin() as connection:
        connection.execute(insert(media_assets).values(**audio.model_dump(by_alias=False)))
        connection.execute(insert(media_assets).values(**shared.model_dump(by_alias=False)))
    attempt = TaskAttempt(
        session_task_id=task.id,
        attempt_number=1,
        input_mode="speech",
        audio_media_asset_id=audio.id,
        response_payload={"transcript": "hola"},
    )
    repository.create_attempt(attempt, owner.id)
    with pytest.raises(TaskConflictError):
        repository.create_attempt(
            attempt.model_copy(
                update={"id": uuid4(), "attempt_number": 2, "audio_media_asset_id": shared.id}
            ),
            owner.id,
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(media_assets)
            .where(media_assets.c.id == audio.id)
            .values(owner_user_id=None, source="preloaded")
        )
    # A valid object from another session must still fail the composite FK.
    other = SessionTask(
        **(task.model_dump(by_alias=False) | {"id": uuid4(), "session_id": uuid4()})
    )
    with pytest.raises(IntegrityError) as failure, engine.begin() as connection:
        # A terminal row keeps this fixture focused on the composite foreign key.
        copied = dict(
            connection.execute(select(sessions).where(sessions.c.id == task.session_id))
            .mappings()
            .one()
        )
        # Mapping iteration uses database column names; writes use SQLAlchemy keys.
        copied.pop("session_status")
        copied.update(id=other.session_id, status="failed", idempotency_key=None)
        connection.execute(insert(sessions).values(**copied))
        connection.execute(insert(session_tasks).values(**entity_values(other)))
    assert failure.value.orig.diag.constraint_name == "session_tasks_scene_object_session_fkey"
    with engine.begin() as connection:
        connection.execute(delete(media_assets).where(media_assets.c.id == shared.id))


@pytest.mark.parametrize("invalid", ["phase", "content", "terminal", "skippable"])
def test_database_rejects_invalid_task_states(context, invalid):
    engine, owner, _, repository, task, _ = context
    repository.create_task(task, owner.id)
    changes = {
        "phase": {"phase": "ispy"},
        "content": {"public_content": {}},
        "terminal": {"status": "completed"},
        "skippable": {"is_skippable": False},
    }
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(session_tasks).where(session_tasks.c.id == task.id).values(**changes[invalid])
        )


def test_task_children_cascade(context):
    engine, owner, client, repository, task, run = context
    attempt = TaskAttempt(
        session_task_id=task.id, attempt_number=1, input_mode="text", response_payload={"text": "a"}
    )
    hint = TaskHint(session_task_id=task.id, hint_level=1, content={"text": "hint"})
    repository.create_task(task, owner.id)
    repository.create_attempt(attempt, owner.id)
    repository.create_hint(hint, owner.id)
    with engine.begin() as connection:
        connection.execute(
            update(session_tasks).where(session_tasks.c.id == task.id).values(status="inProgress")
        )
    assert repository.get(task.id, owner.id).status == "inProgress"
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.id == task.session_id))
        assert (
            connection.execute(
                select(task_attempts).where(task_attempts.c.id == attempt.id)
            ).first()
            is None
        )
        assert (
            connection.execute(select(task_hints).where(task_hints.c.id == hint.id)).first() is None
        )


def test_terminal_sessions_block_new_records_and_rls(context):
    engine, owner, client, repository, task, run = context
    repository.create_task(task, owner.id)
    assert client.post(f"/api/v1/sessions/{task.session_id}/abandon").status_code == 200
    with pytest.raises(TaskConflictError):
        repository.create_hint(
            TaskHint(session_task_id=task.id, hint_level=1, content={}), owner.id
        )
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT relname, relrowsecurity FROM pg_class WHERE oid IN "
                "('public.session_tasks'::regclass,'public.task_attempts'::regclass,"
                "'public.task_hints'::regclass)"
            )
        ).all()
        assert len(rows) == 3 and all(row.relrowsecurity for row in rows)


def test_validation_and_safe_storage_errors():
    with pytest.raises(ValidationError):
        TaskAttempt(
            session_task_id=uuid4(), attempt_number=1, input_mode="speech", response_payload={}
        )
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("select", {}, Exception("secret"))
    with pytest.raises(TaskStorageError, match="Unable to load tasks"):
        PostgresTaskRepository(engine).get(uuid4(), uuid4())
