"""Friend consent, private invitations and direct asynchronous challenges."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from test_rooms import command, create
from test_rooms import db as db

from app.api.dependencies import get_friend_repository
from app.api.routes.friends import router
from app.repositories.postgres.friends import (
    PostgresFriendRepository,
    friend_invitations,
    friendships,
)
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.rooms import RoomError, learning_rooms, room_members
from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.friends import FriendAcceptRequest, FriendInviteRequest
from app.schemas.rooms import CreateRoomRequest


def friends(db):
    return [PostgresFriendRepository(db.engine, person.id) for person in db.people]


def befriend(db, owner=0, acceptor=1):
    repos = friends(db)
    invite = repos[owner].invite(FriendInviteRequest(command_id=uuid4()))
    request = FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code)
    return repos, invite, request, repos[acceptor].accept(request)


def test_friend_invitation_requires_explicit_acceptance_and_survives_restart(db):
    repos = friends(db)
    command_id = uuid4()
    invite = repos[0].invite(FriendInviteRequest(command_id=command_id))
    assert len(invite.invite_code) == 64 and invite.expires_at > utc_now() + timedelta(days=6)
    assert repos[0].list() == repos[1].list() == []
    restarted = PostgresFriendRepository(db.engine, db.people[0].id)
    assert restarted.invite(FriendInviteRequest(command_id=command_id)) == invite
    accepted = repos[1].accept(
        FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code)
    )
    assert accepted.user_id == db.people[0].id and accepted.can_challenge
    assert accepted.model_dump(mode="json") == {
        "userId": str(db.people[0].id),
        "displayName": db.people[0].display_name,
        "sourceLanguageCode": "en",
        "targetLanguageCode": "es",
        "proficiencyLevel": "A1",
        "canChallenge": True,
    }
    assert [friend.user_id for friend in repos[0].list()] == [db.people[1].id]
    assert [friend.user_id for friend in repos[1].list()] == [db.people[0].id]
    assert repos[2].list() == []


def test_friend_link_is_single_use_and_cannot_readd_after_unlink(db):
    repos, invite, request, _ = befriend(db)
    assert repos[1].accept(request).user_id == db.people[0].id
    with pytest.raises(RoomError) as error:
        repos[2].accept(FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code))
    assert error.value.code == "friend_invite_used"
    repos[0].remove(db.people[1].id)
    repos[0].remove(db.people[1].id)
    assert repos[0].list() == repos[1].list() == []
    with pytest.raises(RoomError) as error:
        repos[1].accept(request)
    assert error.value.code == "friend_invite_used"
    assert repos[1].list() == []
    new_invite = repos[1].invite(FriendInviteRequest(command_id=uuid4()))
    assert (
        repos[0]
        .accept(
            FriendAcceptRequest(
                command_id=uuid4(),
                invite_code=new_invite.invite_code,
            )
        )
        .user_id
        == db.people[1].id
    )


def test_friend_link_rejects_self_invalid_expired_and_reused_command(db):
    repos = friends(db)
    first = repos[0].invite(FriendInviteRequest(command_id=uuid4()))
    with pytest.raises(RoomError) as error:
        repos[0].accept(FriendAcceptRequest(command_id=uuid4(), invite_code=first.invite_code))
    assert error.value.code == "friend_invite_self"
    with pytest.raises(RoomError) as error:
        repos[1].accept(FriendAcceptRequest(command_id=uuid4(), invite_code="a" * 64))
    assert error.value.code == "friend_invite_invalid"
    request = FriendAcceptRequest(command_id=uuid4(), invite_code=first.invite_code)
    repos[1].accept(request)
    second = repos[2].invite(FriendInviteRequest(command_id=uuid4()))
    with pytest.raises(RoomError) as error:
        repos[1].accept(request.model_copy(update={"invite_code": second.invite_code}))
    assert error.value.code == "friend_command_conflict"
    with db.engine.begin() as c:
        c.execute(
            update(friend_invitations)
            .where(
                friend_invitations.c.invite_code == second.invite_code,
            )
            .values(
                created_at=utc_now() - timedelta(days=8),
                expires_at=utc_now() - timedelta(seconds=1),
            )
        )
    with pytest.raises(RoomError) as error:
        repos[1].accept(FriendAcceptRequest(command_id=uuid4(), invite_code=second.invite_code))
    assert error.value.code == "friend_invite_expired"


def test_friend_generation_rate_limit_allows_safe_replays(db):
    repo = friends(db)[0]
    first = FriendInviteRequest(command_id=uuid4())
    invite = repo.invite(first)
    for _ in range(9):
        repo.invite(FriendInviteRequest(command_id=uuid4()))
    with pytest.raises(RoomError) as error:
        repo.invite(FriendInviteRequest(command_id=uuid4()))
    assert error.value.code == "friend_rate_limited"
    assert repo.invite(first) == invite


def test_concurrent_friend_acceptance_records_one_mutual_relationship(db):
    repos = friends(db)
    invite = repos[0].invite(FriendInviteRequest(command_id=uuid4()))
    request = FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(pool.map(lambda _: repos[1].accept(request), range(2)))
    assert accepted[0] == accepted[1]
    with db.engine.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(friendships)
                .where(
                    (friendships.c.user_low_id == db.people[0].id)
                    | (friendships.c.user_high_id == db.people[0].id),
                )
            ).scalar_one()
            == 1
        )
    assert len(repos[0].list()) == len(repos[1].list()) == 1


def test_direct_challenge_requires_mutual_friend_and_matching_active_profile(db):
    request = CreateRoomRequest(
        command_id=uuid4(),
        language_profile_id=db.profiles[0].id,
        friend_user_id=db.people[1].id,
    )
    with pytest.raises(RoomError) as error:
        db.repos[0].create(request)
    assert error.value.code == "room_friend_required"
    repos, _, _, _ = befriend(db)
    with db.engine.begin() as c:
        c.execute(
            update(language_profiles)
            .where(
                language_profiles.c.id == db.profiles[1].id,
            )
            .values(proficiency_level="A2")
        )
    assert not repos[0].list()[0].can_challenge
    with pytest.raises(RoomError) as error:
        db.repos[0].create(request)
    assert error.value.code == "room_language_mismatch"
    with db.engine.begin() as c:
        c.execute(
            update(language_profiles)
            .where(
                language_profiles.c.id == db.profiles[1].id,
            )
            .values(proficiency_level="A1")
        )
    access = db.repos[0].create(request)
    assert len(access.room.members) == 2
    assert not any(member.ready for member in access.room.members)
    assert len(db.repos[1].list()) == 1 and db.repos[1].list()[0].id == access.room.id
    assert db.repos[2].list() == []
    assert db.repos[0].create(request).room.id == access.room.id
    # Unlinking prevents new challenges, while an existing challenge can still be resumed or ended.
    repos[1].remove(db.people[0].id)
    assert db.repos[1].get(access.room.id).status == "lobby"
    with pytest.raises(RoomError) as error:
        db.repos[0].create(request.model_copy(update={"command_id": uuid4()}))
    assert error.value.code == "room_friend_required"
    db.repos[1].leave(access.room.id, command(access.room))


def test_direct_challenge_respects_invited_friends_active_limit(db):
    befriend(db)
    for _ in range(10):
        room = create(db, actor=1).room
        with db.engine.begin() as c:
            c.execute(
                update(room_members)
                .where(room_members.c.room_id == room.id)
                .values(
                    joined_at=utc_now() - timedelta(hours=2),
                )
            )
    request = CreateRoomRequest(
        command_id=uuid4(),
        language_profile_id=db.profiles[0].id,
        friend_user_id=db.people[1].id,
    )
    with pytest.raises(RoomError) as error:
        db.repos[0].create(request)
    assert error.value.code == "room_active_limit" and db.repos[0].list() == []
    latest = db.repos[1].active()
    with db.engine.begin() as c:
        c.execute(
            update(learning_rooms)
            .where(learning_rooms.c.id == latest.id)
            .values(
                created_at=utc_now() - timedelta(days=8),
                expires_at=utc_now() - timedelta(seconds=1),
            )
        )
    assert db.repos[0].create(request).room.status == "lobby"


def test_deleting_account_cascades_friendships_and_owned_invitations(db):
    repos, _, request, _ = befriend(db)
    with db.engine.begin() as c:
        c.execute(delete(media_assets).where(media_assets.c.owner_user_id == db.people[0].id))
        c.execute(delete(users).where(users.c.id == db.people[0].id))
    assert repos[1].list() == []
    with pytest.raises(RoomError) as error:
        repos[1].accept(request)
    assert error.value.code == "friend_invite_invalid"
    with db.engine.connect() as c:
        assert not c.execute(
            select(friendships.c.id).where(
                (friendships.c.user_low_id == db.people[0].id)
                | (friendships.c.user_high_id == db.people[0].id),
            )
        ).first()
        assert not c.execute(
            select(friend_invitations.c.id).where(
                friend_invitations.c.owner_user_id == db.people[0].id,
            )
        ).first()


def test_friends_api_returns_only_public_fields_and_supports_unlink(db):
    repos, _, _, _ = befriend(db)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_friend_repository] = lambda: repos[0]
    client = TestClient(app)
    response = client.get("/api/v1/friends")
    assert response.status_code == 200
    assert set(response.json()[0]) == {
        "userId",
        "displayName",
        "sourceLanguageCode",
        "targetLanguageCode",
        "proficiencyLevel",
        "canChallenge",
    }
    invite = client.post("/api/v1/friends/invite", json={"commandId": str(uuid4())})
    assert invite.status_code == 201 and len(invite.json()["inviteCode"]) == 64
    assert client.delete(f"/api/v1/friends/{db.people[1].id}").status_code == 204
    assert client.get("/api/v1/friends").json() == []


def test_friend_acceptance_rate_limit_preserves_invite_for_retry(db, monkeypatch):
    import app.repositories.postgres.friends as friend_module

    repos = friends(db)
    request = None
    for index in range(21):
        owner = (0, 2, 3)[index % 3]
        invite = repos[owner].invite(FriendInviteRequest(command_id=uuid4()))
        request = FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code)
        if index < 20:
            repos[1].accept(request)
    with pytest.raises(RoomError) as error:
        repos[1].accept(request)
    assert error.value.code == "friend_rate_limited"
    later = utc_now() + timedelta(hours=2)
    monkeypatch.setattr(friend_module, "utc_now", lambda: later)
    assert repos[1].accept(request).user_id == db.people[(0, 2, 3)[20 % 3]].id


def test_deleting_acceptor_does_not_make_consumed_friend_link_reusable(db):
    repos, invite, _, _ = befriend(db)
    with db.engine.begin() as c:
        c.execute(delete(media_assets).where(media_assets.c.owner_user_id == db.people[1].id))
        c.execute(delete(users).where(users.c.id == db.people[1].id))
    assert repos[0].list() == []
    with pytest.raises(RoomError) as error:
        repos[2].accept(FriendAcceptRequest(command_id=uuid4(), invite_code=invite.invite_code))
    assert error.value.code == "friend_invite_used"
