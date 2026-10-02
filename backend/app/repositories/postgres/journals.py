"""Five relational journal entities, written atomically under a per-user lock."""

from collections.abc import Callable
from datetime import date
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import (
    Column,
    Connection,
    Date,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories.journals import JournalConflictError, JournalStorageError, validate_entries
from app.repositories.postgres.users import users
from app.schemas.journals import (
    Journal,
    JournalDetailResponse,
    JournalMedia,
    JournalRevision,
    JournalSuggestion,
    JournalWordMention,
)


def entity_columns():
    return [
        Column("id", Uuid, primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    ]


journals = Table(
    "journals",
    MetaData(),
    *entity_columns(),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid, nullable=False),
    Column("local_date", Date, nullable=False),
    Column("timezone", Text, nullable=False),
    Column("title", String(200), nullable=False),
    Column("selected_words", JSONB, nullable=False),
    Column("status", String(9), nullable=False),
    Column("current_revision_id", Uuid),
    Column("audio_media_asset_id", Uuid),
    Column("completed_at", DateTime(timezone=True)),
    schema="public",
)
journal_media = Table(
    "journal_media",
    MetaData(),
    *entity_columns(),
    Column("journal_id", Uuid, nullable=False),
    Column("media_asset_id", Uuid, nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("caption", String(1000)),
    schema="public",
)
journal_revisions = Table(
    "journal_revisions",
    MetaData(),
    *entity_columns(),
    Column("journal_id", Uuid, nullable=False),
    Column("revision_number", Integer, nullable=False),
    Column("content", String(20000), nullable=False),
    Column("created_by", String(6), nullable=False),
    schema="public",
)
journal_suggestions = Table(
    "journal_suggestions",
    MetaData(),
    *entity_columns(),
    Column("journal_id", Uuid, nullable=False),
    Column("base_revision_id", Uuid, nullable=False),
    Column("suggestion_type", String(10), nullable=False),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
    Column("original_text", Text, nullable=False),
    Column("suggested_text", Text, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("status", String(8), nullable=False),
    schema="public",
)
journal_word_mentions = Table(
    "journal_word_mentions",
    MetaData(),
    *entity_columns(),
    Column("journal_revision_id", Uuid, nullable=False),
    Column("vocabulary_item_id", Uuid, nullable=False),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
    Column("matched_text", Text, nullable=False),
    Column("match_method", String(13), nullable=False),
    Column("source_encounter_id", Uuid),
    schema="public",
)

CHILDREN = [
    ("revisions", journal_revisions, JournalRevision, "revision_number"),
    ("media", journal_media, JournalMedia, "display_order"),
    ("suggestions", journal_suggestions, JournalSuggestion, "created_at"),
    ("word_mentions", journal_word_mentions, JournalWordMention, "start_offset"),
]


def entity_groups(rows):
    groups = [(journals, [entry.journal for entry in rows])]
    groups.extend(
        (table, [record for entry in rows for record in getattr(entry, name)])
        for name, table, _, _ in CHILDREN
    )
    return groups


def insert_entries(connection: Connection, rows: list[JournalDetailResponse]) -> None:
    """Journal's current-revision FK is deferred until all child rows exist."""
    validate_entries(rows)
    for table, records in entity_groups(rows):
        for record in records:
            connection.execute(insert(table).values(**record.model_dump(by_alias=False)))


class PostgresJournalRepository:
    def __init__(self, engine: Engine, user_id: UUID) -> None:
        self.engine = engine
        self.user_id = user_id

    def _read(
        self,
        connection: Connection,
        *,
        journal_ids: list[UUID] | None = None,
        local_date: date | None = None,
        limit: int | None = None,
    ) -> list[JournalDetailResponse]:
        statement = select(journals).where(journals.c.user_id == self.user_id)
        if journal_ids is not None:
            statement = statement.where(journals.c.id.in_(journal_ids))
        if local_date is not None:
            statement = statement.where(journals.c.local_date == local_date)
        statement = statement.order_by(journals.c.local_date.desc())
        if limit is not None:
            statement = statement.limit(limit)
        entries = {
            row["id"]: JournalDetailResponse(journal=Journal.model_validate(dict(row)))
            for row in connection.execute(statement).mappings()
        }
        if not entries:
            return []
        ids = list(entries)
        revision_owners = {}
        for name, table, model, order in CHILDREN:
            if table is journal_word_mentions:
                statement = (
                    select(table)
                    .join(journal_revisions, table.c.journal_revision_id == journal_revisions.c.id)
                    .join(journals, journal_revisions.c.journal_id == journals.c.id)
                    .where(journals.c.id.in_(ids))
                )
            else:
                statement = select(table).where(table.c.journal_id.in_(ids))
            for row in connection.execute(
                statement.order_by(table.c[order], table.c.id)
            ).mappings():
                record = model.model_validate(dict(row))
                owner = (
                    revision_owners[record.journal_revision_id]
                    if table is journal_word_mentions
                    else record.journal_id
                )
                getattr(entries[owner], name).append(record)
                if table is journal_revisions:
                    revision_owners[record.id] = owner
        result = list(entries.values())
        validate_entries(result)
        return result

    def read(self) -> list[JournalDetailResponse]:
        try:
            with self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                return self._read(connection)
        except (SQLAlchemyError, ValueError) as exc:
            raise JournalStorageError("Unable to read journals.") from exc

    def read_for_user(self, limit: int | None = None) -> list[JournalDetailResponse]:
        try:
            with self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                return self._read(connection, limit=limit)
        except (SQLAlchemyError, ValueError) as exc:
            raise JournalStorageError("Unable to read journals.") from exc

    def read_one(self, journal_id: UUID) -> JournalDetailResponse | None:
        try:
            with self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                rows = self._read(connection, journal_ids=[journal_id])
                return rows[0] if rows else None
        except (SQLAlchemyError, ValueError) as exc:
            raise JournalStorageError("Unable to read journals.") from exc

    def read_for_date(self, local_date: date) -> JournalDetailResponse | None:
        try:
            with self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                rows = self._read(connection, local_date=local_date)
                return rows[0] if rows else None
        except (SQLAlchemyError, ValueError) as exc:
            raise JournalStorageError("Unable to read journals.") from exc

    def change[T](self, action: Callable[[list[JournalDetailResponse]], T]) -> T:
        try:
            with self.engine.begin() as connection:
                if (
                    connection.execute(
                        select(users.c.id).where(users.c.id == self.user_id).with_for_update()
                    ).scalar_one_or_none()
                    is None
                ):
                    raise JournalStorageError("Journal user does not exist.")
                rows = self._read(connection)
                before = {
                    table.name: {record.id: record.model_dump(by_alias=False) for record in records}
                    for table, records in entity_groups(rows)
                }
                result = action(rows)
                TypeAdapter(list[JournalDetailResponse]).validate_python(
                    [entry.model_dump() for entry in rows]
                )
                validate_entries(rows)
                if any(entry.journal.user_id != self.user_id for entry in rows):
                    raise JournalConflictError("Cannot change journal ownership.")
                for table, records in entity_groups(rows):
                    prior = before[table.name]
                    ids = {record.id for record in records}
                    if len(ids) != len(records):
                        raise JournalConflictError("Duplicate journal child IDs.")
                    removed = set(prior) - ids
                    if removed:
                        if table is not journal_media:
                            raise JournalConflictError("Journal history cannot be removed.")
                        connection.execute(delete(table).where(table.c.id.in_(removed)))
                    for record in records:
                        values = record.model_dump(by_alias=False)
                        old = prior.get(record.id)
                        if old == values:
                            continue
                        if old is not None:
                            mutable = {
                                "journals": {
                                    "title",
                                    "selected_words",
                                    "status",
                                    "current_revision_id",
                                    "audio_media_asset_id",
                                    "completed_at",
                                    "updated_at",
                                },
                                "journal_media": {"caption", "display_order", "updated_at"},
                                "journal_suggestions": {"status", "updated_at"},
                            }.get(table.name, set())
                            if any(values[key] != old[key] for key in values if key not in mutable):
                                raise JournalConflictError(
                                    "Journal history and parent references are immutable."
                                )
                            statement = (
                                update(table).where(table.c.id == record.id).values(**values)
                            )
                        else:
                            statement = insert(table).values(**values)
                        record.updated_at = connection.execute(
                            statement.returning(table.c.updated_at)
                        ).scalar_one()
                return result
        except IntegrityError as exc:
            raise JournalConflictError(
                "Journal record conflicts with its references or current state."
            ) from exc
        except (SQLAlchemyError, ValidationError, ValueError) as exc:
            raise JournalStorageError("Unable to save journals.") from exc
