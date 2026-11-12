"""Weekly progress follows the same target language as lifetime progress."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert
from test_postgres_sessions import database as database

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import SessionBackedLearningRepository
from app.repositories.postgres.users import users
from app.repositories.postgres.xp import award, xp_events
from app.schemas.users import LanguageProfile, User


@pytest.fixture
def fixed_week(monkeypatch):
    class WeekClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 21, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("app.repositories.postgres.practice.datetime", WeekClock)
    return datetime(2026, 10, 19, tzinfo=UTC)


def test_weekly_progress_changes_with_active_language(database, fixed_week):
    engine, owner, spanish, client = database
    competitor = User(display_name=f"Other learner {uuid4()}", auth_provider_id=f"test-{uuid4()}")
    french = LanguageProfile(
        user_id=owner.id, source_language_code="en", target_language_code="fr",
        proficiency_level="A1", is_active=False,
    )
    german = french.model_copy(update={"id": uuid4(), "target_language_code": "de"})
    other_spanish = spanish.model_copy(update={"id": uuid4(), "user_id": competitor.id})
    other_french = french.model_copy(update={"id": uuid4(), "user_id": competitor.id})
    try:
        with engine.begin() as connection:
            connection.execute(insert(users).values(**competitor.model_dump(by_alias=False)))
            connection.execute(insert(language_profiles), [
                profile.model_dump(by_alias=False)
                for profile in (french, german, other_spanish, other_french)
            ])
            for profile, event_type in (
                (spanish, "taskCompleted"), (french, "journalEntry"),
                (other_spanish, "journalEntry"), (other_french, "taskCompleted"),
            ):
                award(
                    connection, user_id=profile.user_id, language_profile_id=profile.id,
                    event_type=event_type, idempotency_key=f"current:{profile.id}",
                    occurred_at=fixed_week + timedelta(days=2),
                )
            award(
                connection, user_id=owner.id, language_profile_id=spanish.id,
                event_type="journalEntry", idempotency_key="previous-week",
                occurred_at=fixed_week - timedelta(microseconds=1),
            )
            award(
                connection, user_id=owner.id, event_type="journalEntry",
                idempotency_key="unscoped", occurred_at=fixed_week + timedelta(days=2),
            )

        for profile, lifetime, weekly, other_weekly in (
            (spanish, 30, 10, 20), (french, 20, 20, 10), (german, 0, 0, None),
        ):
            switched = client.patch(
                f"/api/v1/me/language-profiles/{profile.id}", json={"isActive": True},
            )
            assert switched.status_code == 200, switched.text
            response = client.get("/api/v1/me/progress")
            assert response.status_code == 200, response.text
            progress = response.json()
            assert progress["xp"] == lifetime
            mine = next(row for row in progress["leaderboard"] if row["isYou"])
            assert mine["xp"] == weekly
            other = next((
                row for row in progress["leaderboard"] if row["name"] == competitor.display_name
            ), None)
            if other_weekly is None:
                assert other is None
            else:
                assert other is not None and other["xp"] == other_weekly

        # An explicitly unfiltered repository read still includes every language.
        repository = SessionBackedLearningRepository(engine, owner.id, None)
        unfiltered = repository.get_progress(owner.id)
        assert unfiltered.xp == 70
        assert next(row for row in unfiltered.leaderboard if row.is_you).xp == 50
    finally:
        with engine.begin() as connection:
            connection.execute(delete(xp_events).where(xp_events.c.user_id == competitor.id))
            connection.execute(delete(users).where(users.c.id == competitor.id))


def test_weekly_progress_includes_the_start_but_not_the_end_of_the_week(database, fixed_week):
    engine, owner, profile, client = database
    with engine.begin() as connection:
        for key, occurred_at in (
            ("before", fixed_week - timedelta(microseconds=1)),
            ("start", fixed_week),
            ("end", fixed_week + timedelta(days=7)),
        ):
            award(
                connection, user_id=owner.id, language_profile_id=profile.id,
                event_type="taskCompleted", idempotency_key=key, occurred_at=occurred_at,
            )
    response = client.get("/api/v1/me/progress")
    assert response.status_code == 200, response.text
    mine = next(row for row in response.json()["leaderboard"] if row["isYou"])
    assert mine["xp"] == 10
