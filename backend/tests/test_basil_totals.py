"""Profile totals count earned Basil consistently across account activity."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, insert, update
from test_postgres_sessions import database as database

from app.repositories.postgres.game_resources import (
    equip_appearance,
    game_resource_events,
    reward_basil,
)
from app.repositories.postgres.users import users
from app.repositories.postgres.xp import award
from app.schemas.users import User


def test_summary_weekly_and_lifetime_basil_share_the_earned_ledger(database, monkeypatch):
    engine, owner, profile, client = database
    # Wednesday in UTC, just before Thursday in the learner's timezone.
    now = datetime(2026, 10, 21, 23, 30, tzinfo=UTC)
    week_start = datetime(2026, 10, 19, tzinfo=UTC)
    monkeypatch.setattr("app.repositories.postgres.gamification.utc_now", lambda: now)
    other = User(display_name="Other chef", auth_provider_id=f"test-{uuid4()}")
    try:
        with engine.begin() as c:
            c.execute(insert(users).values(**other.model_dump(by_alias=False)))
            c.execute(update(users).where(users.c.id == owner.id).values(timezone="Asia/Singapore"))
            # Monday inclusive, next Monday exclusive; each source is real Basil,
            # including activity that has no corresponding legacy XP award.
            for source, amount, occurred_at in (
                ("old", 30, week_start - timedelta(microseconds=1)),
                ("mission", 10, week_start),
                ("room", 5, now),
                ("daily-challenge", 20, now),
                ("next-week", 7, week_start + timedelta(days=7)),
            ):
                reward_basil(c, owner.id, source, amount=amount)
                c.execute(update(game_resource_events).where(
                    game_resource_events.c.user_id == owner.id,
                    game_resource_events.c.source_key == f"basil:{source}",
                ).values(created_at=occurred_at))
            # Purchases affect balance, not the amount earned in either period.
            equip_appearance(c, owner.id, "herb", uuid4())
            reward_basil(c, other.id, "other-user", amount=99)
            award(c, user_id=owner.id, language_profile_id=profile.id,
                  event_type="journalEntry", idempotency_key="legacy-xp")

        response = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}")
        assert response.status_code == 200, response.text
        basil = response.json()["basil"]
        assert basil["today"] == 25
        assert basil["weekly"] == 35
        assert basil["lifetime"] == 72
        assert basil["balance"] == 52
        assert basil["competitionDay"] == "2026-10-21"
        assert basil["weekly"] <= basil["lifetime"]
    finally:
        with engine.begin() as c:
            c.execute(delete(users).where(users.c.id == other.id))


def test_summary_basil_is_zero_for_an_account_without_rewards(database):
    _engine, _owner, profile, client = database
    response = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}")
    assert response.status_code == 200, response.text
    basil = response.json()["basil"]
    assert {key: basil[key] for key in ("today", "weekly", "lifetime", "balance")} == {
        "today": 0, "weekly": 0, "lifetime": 0, "balance": 0,
    }
