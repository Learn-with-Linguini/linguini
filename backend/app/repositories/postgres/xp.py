"""XP ledger: every award is a persisted, idempotent event."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import insert

from app.schemas.base import utc_now
from app.schemas.enums import XpEventType
from app.schemas.progress import XpEvent

metadata = MetaData()

xp_events = Table(
    "xp_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid),
    Column("session_id", Uuid),
    Column("event_type", String(20), nullable=False),
    Column("amount", Integer, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)

XP_AMOUNTS = {
    "taskCompleted": 10,
    "ispyCorrect": 15,
    "sessionCompleted": 20,
    "perfectSession": 10,
    "journalEntry": 20,
}


def award(
    connection,
    *,
    user_id: UUID,
    event_type: str,
    idempotency_key: str,
    language_profile_id: UUID | None = None,
    session_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> int:
    """Insert one ledger row; the unique key makes replays a no-op worth 0."""
    event = XpEvent(
        user_id=user_id,
        language_profile_id=language_profile_id,
        session_id=session_id,
        event_type=XpEventType(event_type),
        amount=XP_AMOUNTS[XpEventType(event_type).value],
        idempotency_key=idempotency_key,
        occurred_at=occurred_at or utc_now(),
    )
    inserted = connection.execute(
        insert(xp_events)
        .values(**event.model_dump(by_alias=False))
        .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        .returning(xp_events.c.id)
    ).scalar_one_or_none()
    return event.amount if inserted else 0
