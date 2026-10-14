"""Real PostgreSQL room state/authorization/race tests; no external AI calls."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.auth import get_current_user_id
from app.api.dependencies import get_room_service
from app.api.routes.rooms import router
from app.database import create_database_engine
from app.repositories.postgres.game_resources import (
    SauceExhaustedError,
    game_accounts,
    game_resource_events,
    resource_snapshot,
    reward_basil,
    spend_sauce,
)
from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.rooms import (
    PostgresRoomRepository,
    RoomError,
    cleanup_room_account,
    learning_rooms,
    room_contributions,
    room_members,
    room_photos,
    room_turns,
)
from app.repositories.postgres.users import users
from app.repositories.postgres.xp import xp_events
from app.schemas.base import utc_now
from app.schemas.media import MediaAsset
from app.schemas.rooms import (
    AddRoomPhotoRequest,
    CreateRoomRequest,
    JoinRoomRequest,
    ReviewRoomPhotoRequest,
    RoomClueRequest,
    RoomCommand,
    RoomGuessRequest,
    RoomReadyRequest,
)
from app.schemas.users import LanguageProfile, User
from app.services.background import InlineBackgroundRunner
from app.services.room_photos import RoomPhotoError
from app.services.rooms import RoomService


class PhotoPreparer:
    def __init__(self):
        self.calls = []

    def analyze(self, photo_id, owner_id, asset, profile):
        self.calls.append(("analysis", photo_id))
        return {
            "version": 1,
            "photoId": str(photo_id),
            "ownerId": str(owner_id),
            "title": "A private photo",
            "summary": "Two objects",
            "moderationPassed": True,
            "contentHash": hashlib.sha256(asset.storage_key.encode()).hexdigest(),
            "objects": [
                {"key": str(uuid4()), "label": "cup", "x": 25, "y": 50, "color": "red"},
                {"key": str(uuid4()), "label": "chair", "x": 75, "y": 50, "color": "blue"},
            ],
            "relations": [],
        }

    def build_pack(self, photo_id, owner_id, profile, analysis, review):
        self.calls.append(("pack", photo_id))
        assert profile["room_id"] and analysis["moderationPassed"]
        return {
            "version": 1,
            "objects": [
                dict(
                    key=o["key"],
                    label=o["label"],
                    word=["taza", "silla"][index],
                    translation=o["label"],
                    marker=index + 1,
                    x=o["x"],
                    y=o["y"],
                )
                for index, o in enumerate(review["objects"])
            ],
            "targets": [
                {
                    "objectKey": o["key"],
                    "clueOptions": [
                        {"id": f"clue-{index}", "text": ["Es roja.", "Es azul."][index]}
                    ],
                }
                for index, o in enumerate(review["objects"])
            ],
        }


class ManualRunner:
    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        self.jobs.append((fn, args))

    def run(self):
        while self.jobs:
            fn, args = self.jobs.pop(0)
            fn(*args)


@pytest.fixture
def db(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated disposable PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("DAILY_SAUCE_CAPACITY", "10")
    engine = create_database_engine()
    if os.getenv("TEST_DATABASE_SCHEMA"):
        engine = engine.execution_options(
            schema_translate_map={"public": os.environ["TEST_DATABASE_SCHEMA"]},
        )
    people, profiles, assets = [], [], []
    for index in range(4):
        person = User(display_name=f"Room tester {index}", auth_provider_id=f"test-{uuid4()}")
        with engine.begin() as c:
            c.execute(insert(users).values(**person.model_dump(by_alias=False)))
        profile = PostgresLanguageProfileRepository(engine).create(
            LanguageProfile(
                user_id=person.id,
                source_language_code="en",
                target_language_code="es",
                proficiency_level="A1",
            )
        )
        people.append(person)
        profiles.append(profile)
        owned = []
        for _ in range(4):
            asset = MediaAsset(
                owner_user_id=person.id,
                source="userUpload",
                media_type="image",
                storage_key=f"users/{person.id}/images/{uuid4()}.jpg",
                mime_type="image/jpeg",
            )
            with engine.begin() as c:
                c.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
            owned.append(asset)
        assets.append(owned)
    preparer = PhotoPreparer()
    repos = [
        PostgresRoomRepository(
            engine, p.id, spend_sauce=spend_sauce, reward_basil=reward_basil
        )
        for p in people
    ]
    services = [
        RoomService(
            r, preparer, InlineBackgroundRunner(), image_reader=lambda asset, width: b"webp-image"
        )
        for r in repos
    ]
    yield SimpleNamespace(
        engine=engine,
        people=people,
        profiles=profiles,
        assets=assets,
        repos=repos,
        services=services,
        preparer=preparer,
    )
    ids = [p.id for p in people]
    with engine.begin() as c:
        room_ids = list(
            c.execute(
                select(room_members.c.room_id).where(
                    room_members.c.user_id.in_(ids),
                )
            ).scalars()
        )
        c.execute(delete(learning_rooms).where(learning_rooms.c.id.in_(room_ids)))
        c.execute(delete(sessions).where(sessions.c.user_id.in_(ids)))
        c.execute(delete(media_assets).where(media_assets.c.owner_user_id.in_(ids)))
        c.execute(delete(users).where(users.c.id.in_(ids)))
    engine.dispose()


def command(snapshot, cls=RoomCommand, **values):
    return cls(command_id=uuid4(), expected_revision=snapshot.revision, **values)


def create(db, actor=0):
    return db.services[actor].create(
        CreateRoomRequest(
            command_id=uuid4(),
            language_profile_id=db.profiles[actor].id,
        )
    )


def paired(db):
    access = create(db)
    db.services[1].join(
        JoinRoomRequest(
            command_id=uuid4(),
            language_profile_id=db.profiles[1].id,
            invite_code=access.invite_code,
        )
    )
    return access.room.id


def add_prepared(db, room_id, actor, asset_index=0):
    service = db.services[actor]
    snapshot = service.get(room_id)
    snapshot = service.add_photo(
        room_id,
        command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[actor][asset_index].id),
    )
    photo = next(p for p in snapshot.photos if p.media_asset_id == db.assets[actor][asset_index].id)
    assert photo.status == "awaitingReview"
    review = {"objects": photo.review["objects"], "relations": photo.review["relations"]}
    snapshot = service.review_photo(
        room_id, photo.id, command(snapshot, ReviewRoomPhotoRequest, review=review)
    )
    assert next(p for p in snapshot.photos if p.id == photo.id).status == "ready"
    return photo.id


def prepared_game(db, count=2):
    room_id = paired(db)
    photo_ids = [add_prepared(db, room_id, index % 2, index // 2) for index in range(count)]
    for actor in (0, 1):
        snapshot = db.services[actor].get(room_id)
        db.services[actor].ready(room_id, command(snapshot, RoomReadyRequest))
    return room_id, photo_ids


def start(db, room_id):
    snapshot = db.services[0].get(room_id)
    return db.services[0].start(room_id, command(snapshot))


def answer_round(db, room_id, index, wrong_first=False):
    sender, guesser = index % 2, 1 - index % 2
    snapshot = db.services[sender].get(room_id)
    turn = snapshot.current_turn
    target = turn.target_object_key
    snapshot = db.services[sender].clue(
        room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id=turn.clue_options[0].id)
    )
    if wrong_first:
        wrong = next(o.key for o in snapshot.current_turn.objects if o.key != target)
        snapshot = db.services[guesser].guess(
            room_id, turn.id, command(snapshot, RoomGuessRequest, object_key=wrong)
        )
        assert snapshot.current_turn.phase == "guess" and snapshot.current_turn.result is None
    request = command(snapshot, RoomGuessRequest, object_key=target)
    snapshot = db.services[guesser].guess(room_id, turn.id, request)
    assert snapshot.current_turn.phase == "reveal"
    assert snapshot.current_turn.result.is_correct
    assert db.services[guesser].guess(room_id, turn.id, request).revision == snapshot.revision
    for actor in (sender, guesser):
        snapshot = db.services[actor].get(room_id)
        snapshot = db.services[actor].acknowledge(room_id, turn.id, command(snapshot))
    return snapshot


@pytest.mark.parametrize("count", [2, 3, 4])
def test_complete_unique_photo_game_records_only_own_contributions(db, count):
    room_id, photo_ids = prepared_game(db, count)
    initial = start(db, room_id)
    assert initial.round_count == count
    assert len(initial.photos) == 1 and initial.current_turn.photo_id == photo_ids[0]
    for index in range(count):
        current = db.services[0].get(room_id)
        assert current.current_turn.photo_id == photo_ids[index]
        final = answer_round(db, room_id, index, wrong_first=index == 0)
    assert final.status == "completed" and final.successful_rounds == count
    assert final.current_turn is None and final.photos == []
    assert sum(c.basil_earned for c in final.contributions) == count * 2
    assert sum(c.xp_earned for c in final.contributions) == count * 15
    with db.engine.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(sessions)
                .where(
                    sessions.c.user_id.in_([p.id for p in db.people]),
                )
            ).scalar_one()
            == 0
        )
        spends = list(
            c.execute(
                select(game_resource_events).where(
                    game_resource_events.c.user_id.in_([p.id for p in db.people[:2]]),
                    game_resource_events.c.kind == "sauceSpend",
                )
            ).mappings()
        )
        assert len(spends) == 2
    assert db.services[0].active() is None and db.services[1].active() is None


def test_create_join_retries_do_not_duplicate_members_or_expose_invite(db):
    request = CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    first = db.services[0].create(request)
    retry = db.services[0].create(request)
    assert first.invite_code == retry.invite_code and first.room.id == retry.room.id
    join = JoinRoomRequest(
        command_id=uuid4(), language_profile_id=db.profiles[1].id, invite_code=first.invite_code
    )
    joined = db.services[1].join(join)
    assert joined.invite_code is None
    assert len(db.services[1].join(join).room.members) == 2
    assert "invite" not in db.services[1].get(first.room.id).model_dump_json().lower()
    assert db.services[0].create(request).room.revision == joined.room.revision


def test_profile_ownership_language_and_one_active_room(db):
    with pytest.raises(RoomError, match="active learning language") as error:
        db.services[0].create(
            CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[1].id)
        )
    assert error.value.code == "room_profile_invalid"
    access = create(db)
    with pytest.raises(RoomError) as error:
        create(db)
    assert error.value.code == "room_already_active"
    with db.engine.begin() as c:
        from app.repositories.postgres.language_profiles import language_profiles

        c.execute(
            update(language_profiles)
            .where(language_profiles.c.id == db.profiles[1].id)
            .values(proficiency_level="A2")
        )
    with pytest.raises(RoomError) as error:
        db.services[1].join(
            JoinRoomRequest(
                command_id=uuid4(),
                language_profile_id=db.profiles[1].id,
                invite_code=access.invite_code,
            )
        )
    assert error.value.code == "room_language_mismatch"
    assert len(db.services[0].get(access.room.id).members) == 1


def test_photo_owner_review_and_moderation_privacy(db):
    room_id = paired(db)
    snapshot = db.services[0].get(room_id)
    with pytest.raises(RoomError) as error:
        db.services[0].add_photo(
            room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[1][0].id)
        )
    assert error.value.code == "room_photo_not_found"
    runner = ManualRunner()
    db.services[0].background = runner
    added = db.services[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    photo_id = added.photos[0].id
    assert added.photos[0].image_url is not None
    peer = db.services[1].get(room_id).photos[0]
    assert peer.image_url is None and peer.media_asset_id is None and peer.review is None
    with pytest.raises(RoomError):
        db.services[1].authorized_photo_asset(db.people[1].id, room_id, photo_id)
    assert (
        db.services[0].authorized_photo_asset(db.people[0].id, room_id, photo_id).id
        == db.assets[0][0].id
    )
    runner.run()
    owner = db.services[0].get(room_id)
    peer = db.services[1].get(room_id).photos[0]
    assert peer.image_url and peer.review is None
    assert (
        db.services[1].authorized_photo_asset(db.people[1].id, room_id, photo_id).id
        == db.assets[0][0].id
    )
    with pytest.raises(RoomError):
        db.services[1].review_photo(
            room_id,
            photo_id,
            command(
                owner,
                ReviewRoomPhotoRequest,
                review={"objects": owner.photos[0].review["objects"], "relations": []},
            ),
        )


def test_hidden_current_target_future_turns_and_future_media(db):
    room_id, photo_ids = prepared_game(db, 4)
    sender = start(db, room_id)
    guesser = db.services[1].get(room_id)
    assert guesser.current_turn.target_object_key is None
    assert guesser.current_turn.clue_options is None
    assert guesser.current_turn.clue is None
    assert len(guesser.photos) == 1
    payload = guesser.model_dump_json()
    for photo_id in photo_ids[1:]:
        assert str(photo_id) not in payload
        with pytest.raises(RoomError):
            db.services[1].authorized_photo_asset(db.people[1].id, room_id, photo_id)
    with pytest.raises(RoomError) as error:
        db.services[1].clue(
            room_id,
            sender.current_turn.id,
            command(sender, RoomClueRequest, clue_option_id=sender.current_turn.clue_options[0].id),
        )
    assert error.value.code == "room_wrong_role"
    with pytest.raises(RoomError):
        db.services[2].get(room_id)


def test_command_fingerprint_stale_revision_and_photo_removal_retry(db):
    room_id = paired(db)
    snapshot = db.services[0].get(room_id)
    request = command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    accepted = db.repos[0].add_photo(room_id, request)
    assert db.repos[0].add_photo(room_id, request).revision == accepted.revision
    changed = request.model_copy(update={"media_asset_id": db.assets[0][1].id})
    with pytest.raises(RoomError) as error:
        db.repos[0].add_photo(room_id, changed)
    assert error.value.code == "room_command_conflict"
    with pytest.raises(RoomError) as error:
        db.repos[0].add_photo(
            room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][1].id)
        )
    assert error.value.code == "room_stale_revision"
    removal = command(accepted)
    removed = db.repos[0].remove_photo(room_id, accepted.photos[0].id, removal)
    assert removed.photos == []
    assert (
        db.repos[0].remove_photo(room_id, accepted.photos[0].id, removal).revision
        == removed.revision
    )


def test_concurrent_seat_join_and_same_command_join(db):
    access = create(db)
    requests = {
        actor: JoinRoomRequest(
            command_id=uuid4(),
            language_profile_id=db.profiles[actor].id,
            invite_code=access.invite_code,
        )
        for actor in (1, 2)
    }

    def join(actor):
        try:
            return db.repos[actor].join(requests[actor])
        except RoomError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(join, (1, 2)))
    assert sum(not isinstance(result, str) for result in outcomes) == 1
    assert all(
        not isinstance(result, str) or result in {"room_full", "room_conflict"}
        for result in outcomes
    )
    joined = next(actor for actor in (1, 2) if not isinstance(outcomes[actor - 1], str))
    with ThreadPoolExecutor(max_workers=4) as pool:
        retried = list(pool.map(lambda _: db.repos[joined].join(requests[joined]), range(4)))
    assert all(len(r.room.members) == 2 for r in retried)


def test_concurrent_correct_guess_awards_once(db):
    room_id, _photos = prepared_game(db)
    snapshot = start(db, room_id)
    turn = snapshot.current_turn
    target = turn.target_object_key
    snapshot = db.services[0].clue(
        room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id=turn.clue_options[0].id)
    )
    request = command(snapshot, RoomGuessRequest, object_key=target)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: db.repos[1].guess(room_id, turn.id, request), range(4)))
    assert len({r.revision for r in outcomes}) == 1
    with db.engine.connect() as c:
        xp = list(
            c.execute(select(xp_events).where(xp_events.c.user_id == db.people[1].id)).mappings()
        )
        assert len(xp) == 1 and xp[0]["amount"] == 15
        assert (
            c.execute(
                select(room_contributions.c.guess_count).where(
                    room_contributions.c.turn_id == turn.id,
                    room_contributions.c.user_id == db.people[1].id,
                )
            ).scalar_one()
            == 1
        )


def test_start_is_atomic_if_either_account_has_no_sauce(db):
    room_id, _photos = prepared_game(db)
    with db.engine.begin() as c:
        for person in db.people[:2]:
            resource_snapshot(c, person.id)
        c.execute(
            update(game_accounts)
            .where(game_accounts.c.user_id == db.people[1].id)
            .values(sauce_remaining=0)
        )
    with pytest.raises(SauceExhaustedError):
        start(db, room_id)
    assert db.services[0].get(room_id).status == "lobby"
    with db.engine.connect() as c:
        assert (
            c.execute(
                select(game_accounts.c.sauce_remaining).where(
                    game_accounts.c.user_id == db.people[0].id,
                )
            ).scalar_one()
            == 10
        )
        assert (
            c.execute(
                select(func.count())
                .select_from(room_turns)
                .where(
                    room_turns.c.room_id == room_id,
                )
            ).scalar_one()
            == 0
        )


def test_photo_leases_restart_retry_and_stale_completion(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    added = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    photo_id = added.photos[0].id
    old = db.repos[0].claim_photo(room_id, photo_id)
    assert db.repos[0].claim_photo(room_id, photo_id) is None
    with db.engine.begin() as c:
        c.execute(
            update(room_photos)
            .where(room_photos.c.id == photo_id)
            .values(claim_expires_at=utc_now() - timedelta(seconds=1))
        )
    restored = PostgresRoomRepository(db.engine, db.people[0].id).get(room_id)
    assert restored.photos[0].retryable and restored.photos[0].status == "failed"
    db.repos[0].retry_photo(room_id, photo_id, command(restored))
    newer = db.repos[0].claim_photo(room_id, photo_id)
    result = db.preparer.analyze(old.photo_id, old.owner_user_id, old.asset, old.profile)
    db.repos[0].finish_photo(old, result=result)
    assert db.repos[0].get(room_id).photos[0].status == "analyzing"
    db.repos[0].finish_photo(newer, result=result)
    assert db.repos[0].get(room_id).photos[0].status == "awaitingReview"


def test_reuploaded_identical_bytes_cannot_form_two_photos(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    first = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    job = db.repos[0].claim_photo(room_id, first.photos[0].id)
    result = db.preparer.analyze(job.photo_id, job.owner_user_id, job.asset, job.profile)
    db.repos[0].finish_photo(job, result=result)
    snapshot = db.repos[1].get(room_id)
    second = db.repos[1].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[1][0].id)
    )
    second_id = next(p.id for p in second.photos if p.owner_user_id == db.people[1].id)
    other_job = db.repos[1].claim_photo(room_id, second_id)
    other_result = db.preparer.analyze(
        other_job.photo_id, other_job.owner_user_id, other_job.asset, other_job.profile
    )
    other_result["contentHash"] = result["contentHash"]
    db.repos[1].finish_photo(other_job, result=other_result)
    photo = next(p for p in db.repos[1].get(room_id).photos if p.id == second_id)
    assert photo.status == "failed" and photo.error_code == "room_photo_duplicate"
    with pytest.raises(RoomError):
        db.repos[0].authorized_photo_asset(db.people[0].id, room_id, second_id)


def test_unsafe_photo_stays_private_and_cannot_retry(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    added = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    job = db.repos[0].claim_photo(room_id, added.photos[0].id)
    db.repos[0].finish_photo(
        job, error=RoomPhotoError("room_photo_unsafe", "Choose another photo.", retryable=False)
    )
    snapshot = db.repos[0].get(room_id)
    assert not snapshot.photos[0].retryable
    with pytest.raises(RoomError):
        db.repos[0].retry_photo(room_id, job.photo_id, command(snapshot))
    assert db.repos[1].get(room_id).photos[0].image_url is None


def test_expiry_survives_restart_releases_slot_and_blocks_media(db):
    room_id = paired(db)
    photo_id = add_prepared(db, room_id, 0)
    with db.engine.begin() as c:
        c.execute(
            update(learning_rooms)
            .where(learning_rooms.c.id == room_id)
            .values(
                expires_at=utc_now() - timedelta(seconds=1),
                created_at=utc_now() - timedelta(hours=1),
            )
        )
    fresh = PostgresRoomRepository(db.engine, db.people[0].id)
    assert fresh.get(room_id).status == "expired" and fresh.active() is None
    with pytest.raises(RoomError):
        fresh.authorized_photo_asset(db.people[0].id, room_id, photo_id)
    new_room = fresh.create(
        CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    )
    assert new_room.room.id != room_id
    with db.engine.connect() as c:
        assert not any(
            c.execute(
                select(room_members.c.active).where(room_members.c.room_id == room_id)
            ).scalars()
        )


@pytest.mark.parametrize("phase", ["lobby", "playing", "completed"])
@pytest.mark.parametrize("deleted_actor", [0, 1])
def test_account_cleanup_revokes_photos_but_retains_partner_rewards(db, phase, deleted_actor):
    room_id, photo_ids = prepared_game(db)
    if phase != "lobby":
        start(db, room_id)
        answer_round(db, room_id, 0)
    if phase == "completed":
        answer_round(db, room_id, 1)
    partner = 1 - deleted_actor
    prior = db.services[partner].get(room_id)
    earned = next(c for c in prior.contributions if c.user_id == db.people[partner].id)
    with db.engine.begin() as c:
        c.execute(
            select(users.c.id).where(users.c.id == db.people[deleted_actor].id).with_for_update()
        ).all()
        cleanup_room_account(c, db.people[deleted_actor].id)
        assert c.execute(select(learning_rooms.c.invite_code).where(
            learning_rooms.c.id == room_id,
        )).scalar_one() is None
        owned = list(
            c.execute(
                select(room_photos).where(
                    room_photos.c.room_id == room_id,
                    room_photos.c.id == photo_ids[deleted_actor],
                )
            ).mappings()
        )
        assert owned[0]["media_asset_id"] is None
        assert owned[0]["analysis"] is None and owned[0]["pack"] is None
        assert owned[0]["content_hash"] is None
        c.execute(
            delete(media_assets).where(media_assets.c.owner_user_id == db.people[deleted_actor].id)
        )
        c.execute(delete(users).where(users.c.id == db.people[deleted_actor].id))
    after = db.services[partner].get(room_id)
    assert after.status in {"ended", "completed"}
    retained = next(c for c in after.contributions if c.user_id == db.people[partner].id)
    assert retained.basil_earned == earned.basil_earned and retained.xp_earned == earned.xp_earned
    with pytest.raises(RoomError):
        db.services[partner].authorized_photo_asset(
            db.people[partner].id, room_id, photo_ids[partner]
        )
    assert db.services[partner].active() is None


def test_leave_and_removed_photo_drop_inflight_job(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    added = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    job = db.repos[0].claim_photo(room_id, added.photos[0].id)
    current = db.repos[0].get(room_id)
    leave = command(current)
    assert db.repos[0].leave(room_id, leave).status == "ended"
    db.repos[0].finish_photo(
        job, result=db.preparer.analyze(job.photo_id, job.owner_user_id, job.asset, job.profile)
    )
    assert db.repos[1].get(room_id).status == "ended"
    assert db.repos[0].leave(room_id, leave).status == "ended"
    with pytest.raises(RoomError):
        db.repos[1].authorized_photo_asset(db.people[1].id, room_id, job.photo_id)


def test_api_requires_actor_and_rejects_room_image_access_outside_membership(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def actor(authorization: str | None = Header(default=None)):
        if authorization not in {f"Bearer {index}" for index in range(4)}:
            raise HTTPException(401, detail={"code": "unauthenticated"})
        return db.people[int(authorization[-1])].id

    def service(user_id: Annotated[object, Depends(get_current_user_id)]):
        return db.services[
            next(index for index, person in enumerate(db.people) if person.id == user_id)
        ]

    app.dependency_overrides[get_current_user_id] = actor
    app.dependency_overrides[get_room_service] = service
    room_id = paired(db)
    photo_id = add_prepared(db, room_id, 0)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/rooms/{room_id}").status_code == 401
        assert (
            client.get(
                f"/api/v1/rooms/{room_id}", headers={"Authorization": "Bearer 2"}
            ).status_code
            == 404
        )
        path = f"/api/v1/rooms/{room_id}/photos/{photo_id}/image"
        image = client.get(path, headers={"Authorization": "Bearer 1"})
        assert image.status_code == 200 and image.content == b"webp-image"
        for width in (320, 640, 1280):
            resized = client.get(f"{path}?width={width}", headers={"Authorization": "Bearer 1"})
            assert resized.status_code == 200 and resized.content == b"webp-image"
        assert image.headers["cache-control"] == "private, no-store"
        assert client.get(path, headers={"Authorization": "Bearer 2"}).status_code == 404
        assert (
            client.get(path + "?width=960", headers={"Authorization": "Bearer 1"}).status_code
            == 422
        )


def test_durable_random_invite_survives_restart_without_external_secret(db, monkeypatch):
    monkeypatch.delenv("ROOM_INVITE_SECRET", raising=False)
    request = CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    access = db.repos[0].create(request)
    code = access.invite_code
    assert len(code) == 64 and all(character in "0123456789abcdef" for character in code)
    with db.engine.connect() as c:
        stored = c.execute(select(learning_rooms).where(
            learning_rooms.c.id == access.room.id,
        )).mappings().one()
    assert stored["invite_code"] == code
    assert stored["invite_hash"] == hashlib.sha256(code.encode()).hexdigest()
    fresh = PostgresRoomRepository(db.engine, db.people[0].id)
    assert fresh.get(access.room.id).invite_code == code
    assert fresh.active().invite_code == code
    replay = fresh.create(request)
    assert replay.invite_code == code and replay.room.invite_code == code
    with pytest.raises(RoomError):
        db.repos[2].get(access.room.id)
    joined = db.repos[1].join(JoinRoomRequest(
        command_id=uuid4(), language_profile_id=db.profiles[1].id, invite_code=code,
    ))
    assert joined.invite_code is None and joined.room.invite_code is None
    assert code not in joined.model_dump_json()


def test_concurrent_create_replays_persist_one_invitation(db):
    request = CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    workers = [PostgresRoomRepository(db.engine, db.people[0].id) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        access = list(pool.map(lambda repo: repo.create(request), workers))
    assert access[0].room.id == access[1].room.id
    assert access[0].invite_code == access[1].invite_code
    with db.engine.connect() as c:
        assert c.execute(select(func.count()).select_from(learning_rooms).where(
            learning_rooms.c.host_user_id == db.people[0].id,
        )).scalar_one() == 1


@pytest.mark.parametrize("revocation", ["leave", "invite_expiry", "room_expiry"])
def test_revoked_invitation_is_erased_and_cannot_be_recovered_by_create_replay(db, revocation):
    request = CreateRoomRequest(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    access = db.repos[0].create(request)
    if revocation == "leave":
        db.services[0].leave(access.room.id, command(access.room))
    else:
        with db.engine.begin() as c:
            values = {"invite_expires_at": utc_now() - timedelta(seconds=1)}
            if revocation == "room_expiry":
                values = {
                    "expires_at": utc_now() - timedelta(seconds=1),
                    "created_at": utc_now() - timedelta(hours=1),
                }
            c.execute(update(learning_rooms).where(
                learning_rooms.c.id == access.room.id,
            ).values(**values))
    fresh = PostgresRoomRepository(db.engine, db.people[0].id)
    assert fresh.get(access.room.id).invite_code is None
    with db.engine.connect() as c:
        assert c.execute(select(learning_rooms.c.invite_code).where(
            learning_rooms.c.id == access.room.id,
        )).scalar_one() is None
    replay = fresh.create(request)
    assert replay.invite_code is None and replay.room.invite_code is None
    assert access.invite_code not in replay.model_dump_json()
    with pytest.raises(RoomError):
        db.repos[1].join(JoinRoomRequest(
            command_id=uuid4(), language_profile_id=db.profiles[1].id,
            invite_code=access.invite_code,
        ))


def test_start_revokes_durable_invite_for_both_players(db):
    room_id, _ = prepared_game(db)
    code = db.repos[0].get(room_id).invite_code
    snapshot = start(db, room_id)
    assert snapshot.invite_code is None
    assert db.repos[0].get(room_id).invite_code is None
    assert db.repos[1].get(room_id).invite_code is None
    with db.engine.connect() as c:
        assert c.execute(select(learning_rooms.c.invite_code).where(
            learning_rooms.c.id == room_id,
        )).scalar_one() is None
    with pytest.raises(RoomError):
        db.repos[2].join(JoinRoomRequest(
            command_id=uuid4(), language_profile_id=db.profiles[2].id, invite_code=code,
        ))


def test_database_rejects_mismatched_invite_hash(db):
    access = create(db)
    with db.engine.begin() as c:
        with pytest.raises(IntegrityError):
            with c.begin_nested():
                c.execute(update(learning_rooms).where(
                    learning_rooms.c.id == access.room.id,
                ).values(invite_code="f" * 64))
    assert db.repos[0].get(access.room.id).invite_code == access.invite_code


def test_invite_migration_rotates_only_live_hosted_lobby_codes_using_core_functions(db):
    """Run the actual migration on an isolated legacy-shaped table, never public data."""
    schema = "room_invite_test_" + uuid4().hex
    migration = (Path(__file__).parents[1] / "prisma" / "migrations"
                 / "20261014000000_room_invites" / "migration.sql").read_text()
    sql = migration.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
    sql = sql.replace("public.learning_rooms", f"{schema}.learning_rooms")
    now = utc_now()
    legacy = [
        ("lobby", uuid4(), now + timedelta(minutes=5)),
        ("lobby", uuid4(), now + timedelta(minutes=5)),
        ("lobby", uuid4(), now - timedelta(seconds=1)),
        ("playing", uuid4(), now + timedelta(minutes=5)),
        ("lobby", None, now + timedelta(minutes=5)),
    ]
    ids, old_hashes = [], []
    with db.engine.begin() as c:
        c.exec_driver_sql(f"CREATE SCHEMA {schema}")
        c.exec_driver_sql(
            f"CREATE TABLE {schema}.learning_rooms (LIKE public.learning_rooms INCLUDING DEFAULTS)"
        )
        c.exec_driver_sql(f"ALTER TABLE {schema}.learning_rooms DROP COLUMN invite_code")
        for status, host, expiry in legacy:
            room_id, old_hash = uuid4(), hashlib.sha256(uuid4().bytes).hexdigest()
            ids.append(room_id)
            old_hashes.append(old_hash)
            c.execute(text(f"""
                INSERT INTO {schema}.learning_rooms
                    (id, host_user_id, source_language_code, target_language_code,
                     proficiency_level, status, invite_hash, invite_expires_at, expires_at)
                VALUES (:id, :host, 'en', 'es', 'A1', :status, :hash, :expiry, :end)
            """), {"id": room_id, "host": host, "status": status, "hash": old_hash,
                   "expiry": expiry, "end": now + timedelta(minutes=30)})
        c.exec_driver_sql(sql)
        rows = {row["id"]: row for row in c.execute(text(
            f"SELECT * FROM {schema}.learning_rooms"
        )).mappings()}
        codes = []
        for index, room_id in enumerate(ids):
            row = rows[room_id]
            if index < 2:
                code = row["invite_code"]
                assert len(code) == 64 and code != old_hashes[index]
                assert row["invite_hash"] == hashlib.sha256(code.encode()).hexdigest()
                assert row["invite_hash"] != old_hashes[index]
                assert row["revision"] == 1
                codes.append(code)
            else:
                assert row["invite_code"] is None and row["invite_hash"] == old_hashes[index]
                assert row["invite_expires_at"] <= utc_now()
        assert len(set(codes)) == 2
        c.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")


def test_photo_count_ready_reset_and_owner_removal(db):
    room_id, photo_ids = prepared_game(db, 4)
    snapshot = db.services[0].get(room_id)
    with pytest.raises(RoomError) as error:
        db.services[0].add_photo(
            room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][2].id)
        )
    assert error.value.code == "room_photo_limit"
    with pytest.raises(RoomError):
        db.services[1].remove_photo(room_id, photo_ids[0], command(snapshot))
    snapshot = db.services[0].remove_photo(room_id, photo_ids[0], command(snapshot))
    assert len(snapshot.photos) == 3 and not any(m.ready for m in snapshot.members)
    with pytest.raises(RoomError) as error:
        db.services[0].start(room_id, command(snapshot))
    assert error.value.code == "room_players_not_ready"


def test_safe_failed_review_can_be_corrected_and_preparation_is_bounded(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    snapshot = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    photo_id = snapshot.photos[0].id
    job = db.repos[0].claim_photo(room_id, photo_id)
    analyzed = db.preparer.analyze(job.photo_id, job.owner_user_id, job.asset, job.profile)
    db.repos[0].finish_photo(job, result=analyzed)
    for attempt in range(3):
        snapshot = db.repos[0].get(room_id)
        review = {"objects": analyzed["objects"], "relations": []}
        review["objects"][0]["x"] = 30 + attempt
        db.repos[0].review_photo(
            room_id, photo_id, command(snapshot, ReviewRoomPhotoRequest, review=review)
        )
        job = db.repos[0].claim_photo(room_id, photo_id)
        db.repos[0].finish_photo(
            job,
            error=RoomPhotoError(
                "room_photo_no_clues",
                "Review the colours and positions.",
            ),
        )
    snapshot = db.repos[0].get(room_id)
    assert snapshot.photos[0].review["objects"][0]["x"] == 32
    with pytest.raises(RoomError) as error:
        db.repos[0].review_photo(
            room_id, photo_id, command(snapshot, ReviewRoomPhotoRequest, review=review)
        )
    assert error.value.code == "room_photo_retry_limit"


def test_expired_or_deleted_photo_claim_cannot_publish(db):
    room_id = paired(db)
    snapshot = db.repos[0].get(room_id)
    snapshot = db.repos[0].add_photo(
        room_id, command(snapshot, AddRoomPhotoRequest, media_asset_id=db.assets[0][0].id)
    )
    photo_id = snapshot.photos[0].id
    job = db.repos[0].claim_photo(room_id, photo_id)
    result = db.preparer.analyze(job.photo_id, job.owner_user_id, job.asset, job.profile)
    with db.engine.begin() as c:
        c.execute(
            update(room_photos)
            .where(room_photos.c.id == photo_id)
            .values(claim_expires_at=utc_now() - timedelta(seconds=1))
        )
    db.repos[0].finish_photo(job, result=result)
    assert db.repos[0].get(room_id).photos[0].status == "failed"
    with db.engine.begin() as c:
        c.execute(select(users.c.id).where(users.c.id == db.people[0].id).with_for_update()).all()
        cleanup_room_account(c, db.people[0].id)
        c.execute(delete(media_assets).where(media_assets.c.owner_user_id == db.people[0].id))
        c.execute(delete(users).where(users.c.id == db.people[0].id))
    with pytest.raises(RoomError) as error:
        db.repos[0].finish_photo(job, result=result)
    assert error.value.code == "room_unauthenticated"
    with db.engine.connect() as c:
        row = c.execute(select(room_photos).where(room_photos.c.id == photo_id)).mappings().one()
        assert row["pack"] is None and row["analysis"] is None and row["media_asset_id"] is None


def test_only_offered_clues_and_current_photo_guesses_can_earn(db):
    room_id, _photos = prepared_game(db)
    snapshot = start(db, room_id)
    turn = snapshot.current_turn
    with pytest.raises(RoomError) as error:
        db.services[0].clue(
            room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id="fabricated-option")
        )
    assert error.value.code == "room_clue_invalid"
    snapshot = db.services[0].clue(
        room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id=turn.clue_options[0].id)
    )
    with pytest.raises(RoomError) as error:
        db.services[1].guess(
            room_id, turn.id, command(snapshot, RoomGuessRequest, object_key="other-photo-object")
        )
    assert error.value.code == "room_guess_invalid"
    own = next(c for c in db.services[1].get(room_id).contributions if c.user_id == db.people[1].id)
    assert own.basil_earned == 0 and own.xp_earned == 0 and own.guesses_made == 0


def test_room_setup_rate_bounds_abandoned_preparations(db):
    for _ in range(5):
        access = create(db)
        db.services[0].leave(access.room.id, command(access.room))
    with pytest.raises(RoomError) as error:
        create(db)
    assert error.value.code == "room_rate_limited"


def test_guess_leave_race_keeps_room_ended_and_awards_at_most_once(db):
    room_id, _photos = prepared_game(db)
    snapshot = start(db, room_id)
    turn = snapshot.current_turn
    snapshot = db.services[0].clue(
        room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id=turn.clue_options[0].id)
    )
    guess = command(snapshot, RoomGuessRequest, object_key=turn.target_object_key)
    leave = command(snapshot)

    def act(which):
        try:
            return (
                db.repos[1].guess(room_id, turn.id, guess)
                if which == "guess"
                else db.repos[0].leave(room_id, leave)
            )
        except RoomError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(act, ("guess", "leave")))
    latest = db.repos[0].get(room_id)
    if latest.status == "playing":
        latest = db.repos[0].leave(room_id, command(latest))
    assert latest.status == "ended" and latest.current_turn is None
    guest = next(c for c in latest.contributions if c.user_id == db.people[1].id)
    assert guest.xp_earned in {0, 15} and guest.basil_earned in {0, 1}
    assert guest.guesses_made in {0, 1}


def test_only_host_can_recover_live_unexpired_invitation(db):
    access = create(db)
    room_id = access.room.id
    assert db.services[0].get(room_id).invite_code == access.invite_code
    assert db.services[0].active().invite_code == access.invite_code
    assert db.services[0].get(room_id).model_dump()["inviteCode"] == access.invite_code
    db.services[1].join(
        JoinRoomRequest(
            command_id=uuid4(),
            language_profile_id=db.profiles[1].id,
            invite_code=access.invite_code,
        )
    )
    guest = db.services[1].get(room_id)
    assert guest.invite_code is None
    assert "inviteCode" not in guest.model_dump() and "invite_code" not in guest.model_dump(
        by_alias=False
    )
    with db.engine.begin() as c:
        c.execute(
            update(learning_rooms)
            .where(learning_rooms.c.id == room_id)
            .values(invite_expires_at=utc_now() - timedelta(seconds=1))
        )
    host = db.services[0].get(room_id)
    assert host.invite_code is None and "inviteCode" not in host.model_dump()
    ended = db.services[0].leave(room_id, command(host))
    assert ended.invite_code is None and "inviteCode" not in ended.model_dump()


def test_active_profile_switch_keeps_room_language_and_reward_profile(db):
    from app.repositories.postgres.language_profiles import language_profiles

    room_id, _photos = prepared_game(db)
    snapshot = start(db, room_id)
    turn = snapshot.current_turn
    snapshot = db.services[0].clue(
        room_id, turn.id, command(snapshot, RoomClueRequest, clue_option_id=turn.clue_options[0].id)
    )
    with db.engine.begin() as c:
        c.execute(
            update(language_profiles)
            .where(language_profiles.c.id == db.profiles[1].id)
            .values(is_active=False)
        )
    new_profile = PostgresLanguageProfileRepository(db.engine).create(
        LanguageProfile(
            user_id=db.people[1].id,
            source_language_code="en",
            target_language_code="fr",
            proficiency_level="A2",
        )
    )
    result = db.services[1].guess(
        room_id, turn.id, command(snapshot, RoomGuessRequest, object_key=turn.target_object_key)
    )
    assert result.target_language_code == "es" and result.proficiency_level == "A1"
    with db.engine.connect() as c:
        profile_id = c.execute(
            select(xp_events.c.language_profile_id).where(
                xp_events.c.user_id == db.people[1].id,
            )
        ).scalar_one()
    assert profile_id == db.profiles[1].id and profile_id != new_profile.id
