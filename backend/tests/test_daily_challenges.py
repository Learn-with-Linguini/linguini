"""Daily photo challenge entry, word counts, and the end-of-day rank bonus."""

from datetime import timedelta
from fractions import Fraction
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select
from test_postgres_sessions import create_with_asset, upload_asset
from test_postgres_sessions import database as database

from app.repositories.postgres import daily_challenges
from app.repositories.postgres.daily_challenges import (
    challenge_day,
    challenge_entries,
    challenge_finds,
    challenge_settlements,
    rank_bonus,
    rarity_ranks,
    record_completion,
    settle_day,
)
from app.repositories.postgres.game_resources import game_resource_events, resource_snapshot
from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_objects
from app.repositories.postgres.users import users
from app.schemas.sessions import Session
from app.schemas.users import LanguageProfile, User


def test_rarer_words_rank_higher_and_ties_share_a_rank():
    a, b, c, d = (uuid4() for _ in range(4))
    ranks = rarity_ranks({
        a: {"coffee", "cup", "window"},
        b: {"coffee", "cup"},
        c: {"coffee", "cup"},
        d: set(),
    })
    # 4 participants: coffee/cup found by 3 score 4/3 each; window found by 1 scores 4.
    assert ranks[a] == (1, Fraction(4, 3) * 2 + 4)
    assert ranks[b][0] == ranks[c][0] == 2
    assert ranks[d] == (4, 0)
    assert [rank_bonus(rank) for rank in (1, 2, 3, 4, 10, 11)] == [50, 30, 20, 10, 10, 5]


def test_challenge_sessions_need_todays_day_and_an_own_photo(database):
    engine, owner, profile, client = database
    asset = upload_asset(engine, owner)
    today = challenge_day()
    body = {
        "languageProfileId": str(profile.id),
        "mediaAssetId": str(asset),
        "idempotencyKey": "challenge-key-1",
    }
    stale = client.post("/api/v1/sessions", json=body | {
        "dailyChallengeDay": (today - timedelta(days=1)).isoformat(),
    })
    assert stale.status_code == 409
    scenes = client.get("/api/v1/preloaded-scenes").json()
    ready = client.post("/api/v1/sessions", json=body | {
        "mediaAssetId": scenes[0]["mediaAsset"]["id"],
        "idempotencyKey": "challenge-key-2",
        "dailyChallengeDay": today.isoformat(),
    })
    assert ready.status_code == 409
    assert client.get("/api/v1/me/daily-challenge").json()["status"] == "notStarted"

    started = client.post("/api/v1/sessions", json=body | {"dailyChallengeDay": today.isoformat()})
    assert started.status_code == 202, started.text
    sid = started.json()["session"]["id"]
    # Retrying the same request does not create a second entry.
    again = client.post("/api/v1/sessions", json=body | {"dailyChallengeDay": today.isoformat()})
    assert again.json()["session"]["id"] == sid
    challenge = client.get("/api/v1/me/daily-challenge").json()
    assert challenge["status"] == "inProgress" and challenge["sessionId"] == sid
    assert challenge["sceneTitle"] == daily_challenges.scene_for(today)[1]
    assert challenge["participantCount"] == 0 and challenge["words"] == []
    assert challenge["joinedCount"] == 1
    assert challenge["scenePhrase"]
    # A normal session with the same photo is not an entry.
    assert create_with_asset(client, profile, asset, "plain-key-1").status_code == 202
    with engine.connect() as c:
        assert c.execute(
            select(challenge_entries.c.session_id).where(challenge_entries.c.user_id == owner.id)
        ).scalars().all() == [UUID(sid)]


def _profile(engine, person):
    return PostgresLanguageProfileRepository(engine).create(LanguageProfile(
        user_id=person.id, source_language_code="en", target_language_code="fr",
        proficiency_level="A1",
    ))


def _learner_session(engine, person, profile, labels, *, entry=True):
    asset = upload_asset(engine, person)
    session = Session(user_id=person.id, language_profile_id=profile.id, scene_media_asset_id=asset)
    with engine.begin() as c:
        c.execute(insert(sessions).values(**session.model_dump(by_alias=False)))
        c.execute(insert(scene_objects), [
            {"id": uuid4(), "session_id": session.id, "label": label} for label in labels
        ])
        if entry:
            daily_challenges.enter_challenge(c, person.id, session.id, challenge_day(), "camera")
    return session.id


def _complete(engine, person, session_id):
    with engine.begin() as c:
        record_completion(c, person.id, session_id)


def test_completed_entries_count_words_once_and_settle_one_bonus_each(database, monkeypatch):
    engine, owner, owner_profile, client = database
    others = [User(display_name=f"Finder {i}", auth_provider_id=str(uuid4())) for i in range(2)]
    with engine.begin() as c:
        c.execute(insert(users), [u.model_dump(by_alias=False) for u in others])
    today = challenge_day()
    try:
        profiles = {owner.id: owner_profile} | {p.id: _profile(engine, p) for p in others}

        def play(person, labels, **kwargs):
            return _learner_session(engine, person, profiles[person.id], labels, **kwargs)

        _complete(engine, owner, play(owner, ["Coffee ", "coffee", "cup", "Window"]))
        # A second completed challenge the same day adds nothing.
        _complete(engine, owner, play(owner, ["unicorn"]))
        for person in others:
            _complete(engine, person, play(person, ["coffee", "cup"]))
        # A normal session never counts, even if completed.
        _complete(engine, others[0], play(others[0], ["dragon"], entry=False))
        late = play(others[1], ["late"])

        live = client.get("/api/v1/me/daily-challenge").json()
        assert live["status"] == "completed" and live["participantCount"] == 3
        assert live["yourWordCount"] == 3
        assert [(w["label"], w["count"], w["foundByYou"]) for w in live["words"]] == [
            ("coffee", 3, True), ("cup", 3, True), ("Window", 1, True),
        ]

        monkeypatch.setattr(
            daily_challenges, "challenge_day", lambda now=None: today + timedelta(days=1)
        )
        after = client.get("/api/v1/me/daily-challenge").json()
        assert after["status"] == "notStarted" and after["words"] == []
        assert after["lastResult"] == {
            "challengeDay": today.isoformat(),
            "sceneTitle": daily_challenges.scene_for(today)[1],
            "rank": 1,
            "participantCount": 3,
            "basil": 50,
        }
        # Settlement is exactly once, and a completion after it is not counted.
        with engine.begin() as c:
            assert settle_day(c, today) is False
        _complete(engine, others[1], late)
        with engine.connect() as c:
            assert resource_snapshot(c, owner.id).basil_leaves == 50
            assert [resource_snapshot(c, p.id).basil_leaves for p in others] == [30, 30]
            assert c.execute(select(challenge_finds.c.label_key).where(
                challenge_finds.c.label_key == "late")).first() is None
    finally:
        with engine.begin() as c:
            ids = [owner.id, *(p.id for p in others)]
            c.execute(delete(challenge_settlements).where(
                challenge_settlements.c.challenge_day == today))
            c.execute(delete(challenge_finds).where(challenge_finds.c.user_id.in_(ids)))
            c.execute(delete(game_resource_events).where(game_resource_events.c.user_id.in_(ids)))
            c.execute(delete(sessions).where(sessions.c.user_id.in_(ids[1:])))
            c.execute(delete(media_assets).where(media_assets.c.owner_user_id.in_(ids[1:])))
            c.execute(delete(users).where(users.c.id.in_(ids[1:])))
