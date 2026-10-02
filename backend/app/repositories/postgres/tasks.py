"""Task persistence for trusted planners/evaluators; no grading logic or public answer keys."""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Uuid,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import read_connection
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.users import users
from app.repositories.tasks import TaskConflictError, TaskNotFoundError, TaskStorageError
from app.schemas.tasks import SessionTask, TaskAttempt, TaskHint


def entity_columns():
    return [
        Column("id", Uuid, primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    ]


session_tasks = Table(
    "session_tasks",
    MetaData(),
    *entity_columns(),
    Column("session_id", Uuid, nullable=False),
    Column("phase", String(8), nullable=False),
    Column("kind", String(22), nullable=False),
    Column("order_index", Integer, nullable=False),
    Column("status", String(10), nullable=False),
    Column("is_skippable", Boolean, nullable=False),
    Column("public_content", JSONB, nullable=False),
    Column("answer_key", JSONB(none_as_null=True)),
    Column("vocabulary_item_id", Uuid),
    Column("scene_object_id", Uuid),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("skipped_at", DateTime(timezone=True)),
    Column("skip_reason", String(500)),
    schema="public",
)

task_attempts = Table(
    "task_attempts",
    MetaData(),
    *entity_columns(),
    Column("session_task_id", Uuid, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("input_mode", String(15), nullable=False),
    Column("response_payload", JSONB, nullable=False),
    Column("audio_media_asset_id", Uuid),
    Column("is_correct", Boolean),
    Column("score", Numeric(6, 5)),
    Column("feedback", JSONB(none_as_null=True)),
    Column("evaluation_details", JSONB(none_as_null=True)),
    schema="public",
)

task_hints = Table(
    "task_hints",
    MetaData(),
    *entity_columns(),
    Column("session_task_id", Uuid, nullable=False),
    Column("hint_level", Integer, nullable=False),
    Column("content", JSONB, nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


def entity_values(record: SessionTask | TaskAttempt | TaskHint) -> dict:
    # Validate again: model_copy(update=...) bypasses Pydantic validation.
    record = type(record).model_validate(record.model_dump(by_alias=False))
    values = record.model_dump(by_alias=False)
    if isinstance(record, TaskAttempt) and record.score is not None:
        values["score"] = record.score.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
    if isinstance(record, SessionTask):
        values["public_content"] = record.public_content.model_dump(mode="json")
        values["answer_key"] = (
            record.answer_key.model_dump(mode="json") if record.answer_key else None
        )
    else:
        serialized = record.model_dump(mode="json", by_alias=False)
        for name in ("response_payload", "feedback", "evaluation_details", "content"):
            if name in values:
                values[name] = serialized[name]
    return values


class PostgresTaskRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _read(self, table, model, user_id, *conditions, order_by=None):
        statement = select(table)
        if table is not session_tasks:
            statement = statement.join(session_tasks, table.c.session_task_id == session_tasks.c.id)
        statement = statement.join(sessions, session_tasks.c.session_id == sessions.c.id).where(
            sessions.c.user_id == user_id, *conditions
        )
        if order_by is not None:
            statement = statement.order_by(order_by)
        try:
            with read_connection(self.engine) as connection:
                return [
                    model.model_validate(dict(row))
                    for row in connection.execute(statement).mappings()
                ]
        except (SQLAlchemyError, ValidationError) as exc:
            raise TaskStorageError("Unable to load tasks.") from exc

    def get(self, task_id: UUID, user_id: UUID) -> SessionTask | None:
        rows = self._read(session_tasks, SessionTask, user_id, session_tasks.c.id == task_id)
        return rows[0] if rows else None

    def list_for_session(self, session_id: UUID, user_id: UUID) -> list[SessionTask]:
        return self._read(
            session_tasks,
            SessionTask,
            user_id,
            sessions.c.id == session_id,
            order_by=session_tasks.c.order_index,
        )

    def list_attempts(self, task_id: UUID, user_id: UUID) -> list[TaskAttempt]:
        return self._read(
            task_attempts,
            TaskAttempt,
            user_id,
            session_tasks.c.id == task_id,
            order_by=task_attempts.c.attempt_number,
        )

    def list_hints(self, task_id: UUID, user_id: UUID) -> list[TaskHint]:
        return self._read(
            task_hints,
            TaskHint,
            user_id,
            session_tasks.c.id == task_id,
            order_by=task_hints.c.hint_level,
        )

    def _create(self, table, record, user_id):
        try:
            values = entity_values(record)
            with self.engine.begin() as connection:
                connection.execute(
                    select(users.c.id).where(users.c.id == user_id).with_for_update()
                )
                parent = select(sessions).where(sessions.c.user_id == user_id)
                if isinstance(record, SessionTask):
                    parent = parent.where(sessions.c.id == record.session_id)
                else:
                    parent = parent.join(
                        session_tasks, session_tasks.c.session_id == sessions.c.id
                    ).where(session_tasks.c.id == record.session_task_id)
                session = (
                    connection.execute(parent.with_for_update(of=sessions)).mappings().one_or_none()
                )
                if session is None:
                    raise TaskNotFoundError("Task or session not found for this user.")
                existing = (
                    connection.execute(select(table).where(table.c.id == record.id))
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if entity_values(type(record).model_validate(dict(existing))) != values:
                        raise TaskConflictError("Entity ID already used for different data.")
                    return type(record).model_validate(dict(existing))
                if session["status"] in {"completed", "abandoned", "failed"}:
                    raise TaskConflictError("Cannot add task records to a terminal session.")
                if not isinstance(record, SessionTask):
                    task_status = connection.execute(
                        select(session_tasks.c.status).where(
                            session_tasks.c.id == record.session_task_id
                        )
                    ).scalar_one()
                    if task_status in {"completed", "skipped"}:
                        raise TaskConflictError("Cannot add attempts or hints to a terminal task.")
                row = (
                    connection.execute(insert(table).values(**values).returning(table))
                    .mappings()
                    .one()
                )
                return type(record).model_validate(dict(row))
        except IntegrityError as exc:
            raise TaskConflictError(
                "Duplicate task position/attempt/hint or invalid reference."
            ) from exc
        except (SQLAlchemyError, ValidationError) as exc:
            raise TaskStorageError("Unable to save task record.") from exc

    def create_task(self, task: SessionTask, user_id: UUID) -> SessionTask:
        return self._create(session_tasks, task, user_id)

    def create_attempt(self, attempt: TaskAttempt, user_id: UUID) -> TaskAttempt:
        return self._create(task_attempts, attempt, user_id)

    def create_hint(self, hint: TaskHint, user_id: UUID) -> TaskHint:
        return self._create(task_hints, hint, user_id)
