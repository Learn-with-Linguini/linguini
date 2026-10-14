"""Account resources; callers use the same transaction as the accepted activity."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.game_resources import GameResourcesResponse, SauceBalance

metadata = MetaData()
game_accounts = Table(
    "game_accounts", metadata,
    Column("user_id", Uuid, primary_key=True),
    Column("sauce_remaining", Integer, nullable=False),
    Column("sauce_capacity", Integer, nullable=False),
    Column("sauce_period_start", DateTime(timezone=True), nullable=False),
    Column("sauce_refills_at", DateTime(timezone=True), nullable=False),
    Column("basil_balance", Integer, nullable=False),
    Column("appearance", String(10), nullable=False),
    Column("owned_appearances", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
game_resource_events = Table(
    "game_resource_events", metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("source_key", Text, nullable=False),
    Column("kind", String(20), nullable=False),
    Column("sauce_delta", Integer, nullable=False),
    Column("basil_delta", Integer, nullable=False),
    Column("sauce_period_start", DateTime(timezone=True)),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


class SauceExhaustedError(Exception):
    def __init__(self, refills_at: datetime) -> None:
        super().__init__("Your Sauce is empty. Resume a lesson or return after the refill.")
        self.refills_at = refills_at


class InsufficientBasilError(Exception):
    pass


class ResourceCommandConflictError(Exception):
    pass


class GameResourcesUnavailableError(Exception):
    pass


def sauce_capacity() -> int:
    try:
        capacity = int(os.getenv("DAILY_SAUCE_CAPACITY", "10"))
    except ValueError as exc:
        raise GameResourcesUnavailableError("Daily Sauce capacity is not configured.") from exc
    if not 1 <= capacity <= 100:
        raise GameResourcesUnavailableError("Daily Sauce capacity must be between 1 and 100.")
    return capacity


def _account(connection, user_id: UUID):
    now = utc_now()
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    capacity = sauce_capacity()
    connection.execute(
        insert(game_accounts).values(
            user_id=user_id, sauce_remaining=capacity, sauce_capacity=capacity,
            sauce_period_start=start, sauce_refills_at=start + timedelta(days=1),
            basil_balance=0, appearance="default", owned_appearances=["default"],
            created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["user_id"])
    )
    row = connection.execute(
        select(game_accounts).where(game_accounts.c.user_id == user_id).with_for_update()
    ).mappings().one()
    if now >= row["sauce_refills_at"]:
        row = connection.execute(
            update(game_accounts).where(game_accounts.c.user_id == user_id).values(
                sauce_remaining=capacity, sauce_capacity=capacity,
                sauce_period_start=start, sauce_refills_at=start + timedelta(days=1),
            ).returning(game_accounts)
        ).mappings().one()
    return row


def _event(connection, user_id, source_key):
    return connection.execute(select(game_resource_events).where(
        game_resource_events.c.user_id == user_id,
        game_resource_events.c.source_key == source_key,
    )).mappings().one_or_none()


def _insert_event(connection, user_id, source_key, kind, *, sauce=0, basil=0,
                  period=None, payload=None):
    connection.execute(insert(game_resource_events).values(
        id=uuid4(), user_id=user_id, source_key=source_key, kind=kind,
        sauce_delta=sauce, basil_delta=basil, sauce_period_start=period,
        payload=payload or {}, created_at=utc_now(),
    ))


def spend_sauce(connection, user_id: UUID, activity_key: str) -> int:
    account = _account(connection, user_id)
    key = f"sauce:{activity_key}"
    if _event(connection, user_id, key):
        return 0
    if account["sauce_remaining"] < 1:
        raise SauceExhaustedError(account["sauce_refills_at"])
    _insert_event(connection, user_id, key, "sauceSpend", sauce=-1,
                  period=account["sauce_period_start"])
    connection.execute(update(game_accounts).where(game_accounts.c.user_id == user_id).values(
        sauce_remaining=game_accounts.c.sauce_remaining - 1,
    ))
    return 1


def refund_sauce(connection, user_id: UUID, activity_key: str) -> int:
    charge = _event(connection, user_id, f"sauce:{activity_key}")
    if charge is None:
        return 0
    account = _account(connection, user_id)
    key = f"refund:{activity_key}"
    if _event(connection, user_id, key):
        return 0
    _insert_event(connection, user_id, key, "sauceRefund", sauce=1,
                  period=charge["sauce_period_start"])
    if account["sauce_period_start"] == charge["sauce_period_start"]:
        connection.execute(update(game_accounts).where(game_accounts.c.user_id == user_id).values(
            sauce_remaining=min(account["sauce_capacity"], account["sauce_remaining"] + 1),
        ))
    return 1


def reward_basil(connection, user_id: UUID, source_key: str) -> int:
    _account(connection, user_id)
    key = f"basil:{source_key}"
    if _event(connection, user_id, key):
        return 0
    _insert_event(connection, user_id, key, "basilEarned", basil=1)
    connection.execute(update(game_accounts).where(game_accounts.c.user_id == user_id).values(
        basil_balance=game_accounts.c.basil_balance + 1,
    ))
    return 1


def resource_snapshot(connection, user_id: UUID) -> GameResourcesResponse:
    row = _account(connection, user_id)
    return GameResourcesResponse(
        sauce=SauceBalance(remaining=row["sauce_remaining"], capacity=row["sauce_capacity"],
                           refills_at=row["sauce_refills_at"]),
        basil_leaves=row["basil_balance"], appearance=row["appearance"],
        owned_appearances=row["owned_appearances"],
    )


def equip_appearance(connection, user_id: UUID, appearance: str, command_id: UUID):
    row = _account(connection, user_id)
    key = f"appearance:{command_id}"
    prior = _event(connection, user_id, key)
    payload = {"appearance": appearance}
    if prior:
        if prior["payload"] != payload:
            raise ResourceCommandConflictError("This request was used for another appearance.")
        return resource_snapshot(connection, user_id)
    owned = list(row["owned_appearances"])
    cost = 0 if appearance in owned else 20
    if row["basil_balance"] < cost:
        raise InsufficientBasilError("Collect 20 Basil leaves to unlock this appearance.")
    if appearance not in owned:
        owned.append(appearance)
    _insert_event(connection, user_id, key, "appearance", basil=-cost, payload=payload)
    connection.execute(update(game_accounts).where(game_accounts.c.user_id == user_id).values(
        basil_balance=row["basil_balance"] - cost, appearance=appearance, owned_appearances=owned,
    ))
    return resource_snapshot(connection, user_id)


def lock_resource_owner(connection, user_id: UUID) -> None:
    if connection.execute(select(users.c.id).where(
        users.c.id == user_id,
    ).with_for_update()).scalar_one_or_none() is None:
        raise GameResourcesUnavailableError("Account not found.")
