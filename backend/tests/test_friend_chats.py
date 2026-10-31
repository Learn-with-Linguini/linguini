"""Persistent friend-chat boundaries, authorization and PostgreSQL transitions."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, select, text, update

from app.database import create_database_engine
from app.repositories.postgres.friend_chats import (
    PostgresFriendChatRepository,
    assistance,
    blocks,
    chats,
    messages,
    reports,
    rounds,
)
from app.repositories.postgres.language_profiles import (
    PostgresLanguageProfileRepository,
    language_profiles,
)
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.room_errors import RoomError
from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.friend_chats import (
    ChatCommand,
    ChatCreate,
    ChatJoin,
    GuessChatTarget,
    ReportChat,
    SelectChatTarget,
    SendChatClue,
    StartChatRound,
)
from app.schemas.media import MediaAsset
from app.schemas.users import LanguageProfile, User


def command(snapshot, cls=ChatCommand, **values):
    return cls(command_id=uuid4(), expected_revision=snapshot.revision, **values)


@pytest.mark.parametrize("coordinate", [-0.01, 1.01, float("nan"), float("inf")])
def test_guess_rejects_coordinates_outside_the_photo(coordinate):
    with pytest.raises(ValidationError):
        GuessChatTarget(command_id=uuid4(), expected_revision=0, x=coordinate, y=.5)
    with pytest.raises(ValidationError):
        GuessChatTarget(command_id=uuid4(), expected_revision=0, x=.5, y=coordinate)


@pytest.mark.parametrize("selection", [
    {}, {"x": .3}, {"y": .5}, {"x": .3, "y": .5, "confirm": True},
    {"objectKey": "detected", "x": .3, "y": .5},
    {"objectKey": "detected", "label": "chair"},
])
def test_target_requests_require_one_selection_and_explicit_custom_review(selection):
    with pytest.raises(ValidationError):
        SelectChatTarget(command_id=uuid4(), expected_revision=0, **selection)


def test_custom_target_and_photo_boundary_coordinates_remain_valid():
    proposal = SelectChatTarget(
        command_id=uuid4(), expected_revision=0, x=0, y=1, label="chair", confirm=False,
    )
    assert proposal.x == 0 and proposal.y == 1 and not proposal.confirm
    confirmation = SelectChatTarget(
        command_id=uuid4(), expected_revision=1, object_key="proposed-object", confirm=True,
    )
    assert confirmation.confirm
    assert GuessChatTarget(command_id=uuid4(), expected_revision=2, x=1, y=0).x == 1


@pytest.mark.parametrize("text", ["", "   ", "a" * 501])
def test_clues_and_report_reasons_are_bounded(text):
    with pytest.raises(ValidationError):
        SendChatClue(command_id=uuid4(), expected_revision=0, text=text)
    with pytest.raises(ValidationError):
        ReportChat(command_id=uuid4(), expected_revision=0, reason=text)


@pytest.fixture
def db(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated disposable PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    if os.getenv("TEST_DATABASE_SCHEMA"):
        engine = engine.execution_options(
            schema_translate_map={"public": os.environ["TEST_DATABASE_SCHEMA"]},
        )
    people, profiles, assets = [], [], []
    for index, (language, level) in enumerate([
        ("es", "A0"), ("es", "A2"), ("fr", "A1"), ("es", "A1"),
    ]):
        person = User(display_name=f"Chat tester {index}", auth_provider_id=f"chat-{uuid4()}")
        with engine.begin() as c:
            c.execute(insert(users).values(**person.model_dump(by_alias=False)))
        profile = PostgresLanguageProfileRepository(engine).create(LanguageProfile(
            user_id=person.id, source_language_code="en", target_language_code=language,
            proficiency_level=level,
        ))
        owned = []
        for _ in range(2):
            asset = MediaAsset(owner_user_id=person.id, source="userUpload", media_type="image",
                storage_key=f"users/{person.id}/images/{uuid4()}.jpg", mime_type="image/jpeg")
            with engine.begin() as c:
                c.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
            owned.append(asset)
        people.append(person)
        profiles.append(profile)
        assets.append(owned)
    repos = [PostgresFriendChatRepository(engine, person.id) for person in people]
    try:
        yield SimpleNamespace(engine=engine, people=people, profiles=profiles, assets=assets,
            repos=repos)
    finally:
        ids = [person.id for person in people]
        with engine.begin() as c:
            c.execute(delete(chats).where(chats.c.creator_user_id.in_(ids)))
            c.execute(delete(media_assets).where(media_assets.c.owner_user_id.in_(ids)))
            c.execute(delete(users).where(users.c.id.in_(ids)))
        engine.dispose()


def create(db, actor=0):
    return db.repos[actor].create(ChatCreate(
        command_id=uuid4(), language_profile_id=db.profiles[actor].id,
    ))


def join(db, access, actor=1):
    return db.repos[actor].join(ChatJoin(command_id=uuid4(),
        language_profile_id=db.profiles[actor].id, invite_token=access.invite_token))


def paired(db):
    access = create(db)
    join(db, access)
    return access


def start(db, chat_id, actor=0, asset_index=0):
    repo = db.repos[actor]
    return repo.start_round(chat_id, command(repo.get(chat_id), StartChatRound,
        media_asset_id=db.assets[actor][asset_index].id))


def photo_content():
    target = {
        "key": str(uuid4()), "label": "cup", "word": "la taza", "translation": "the cup",
        "x": .25, "y": .4, "width": .2, "height": .3,
        "region": {"x": .15, "y": .25, "width": .2, "height": .3},
        "attributes": {"color": "red", "size": "small"},
        "privateProviderContext": "Never send this field to a learner.",
    }
    other = {
        "key": str(uuid4()), "label": "chair", "word": "la silla", "translation": "the chair",
        "x": .75, "y": .7, "width": .25, "height": .25,
    }
    options = [{"id": "small", "text": "Es pequeña.", "translation": "It is small.",
        "concept": "adjective", "cheatSheet": {
            "missionId": "M02", "practiceLevel": "A0", "contentVersion": 2,
        }}]
    return {"objects": [target, other], "storageKey": "private/storage/path"}, target, options


def prepared(db, chat_id, actor=0):
    repo = db.repos[actor]
    snapshot = start(db, chat_id, actor)
    round_id = snapshot.active_round.id
    job = repo.claim_photo(chat_id, round_id)
    content, target, options = photo_content()
    repo.finish_photo(job, content=content)
    snapshot = repo.get(chat_id)
    snapshot = repo.select_target(chat_id, round_id,
        command(snapshot, SelectChatTarget, object_key=target["key"], confirm=True),
        target, options)
    return snapshot, target, options


def awaiting_guess(db, chat_id, actor=0):
    snapshot, target, options = prepared(db, chat_id, actor)
    repo = db.repos[actor]
    snapshot = repo.send_clue(chat_id, snapshot.active_round.id,
        command(snapshot, SendChatClue, text="Es pequeña."), "Es pequeña.")
    return snapshot, target, options


def count(db, table, condition):
    with db.engine.connect() as c:
        return c.execute(select(func.count()).select_from(table).where(condition)).scalar_one()


def test_mixed_levels_join_without_exposing_the_friends_proficiency(db):
    access = create(db)
    preview = db.repos[1].preview(access.invite_token)
    assert preview.status == "open" and preview.creator.id == db.people[0].id
    guest = join(db, access)
    host = db.repos[0].get(access.chat.id)
    assert guest.status == host.status == "active"
    assert host.viewer_level == "A0" and guest.viewer_level == "A2"
    assert guest.partner.id == db.people[0].id and host.partner.id == db.people[1].id
    assert "proficiencyLevel" not in host.partner.model_dump(by_alias=True)
    assert "proficiencyLevel" not in guest.creator.model_dump(by_alias=True)
    assert "inviteToken" not in guest.model_dump(by_alias=True)
    assert PostgresFriendChatRepository(db.engine, db.people[0].id).get(host.id) == host


def test_language_mismatch_does_not_activate_or_replace_any_profile(db):
    access = create(db)
    with pytest.raises(RoomError) as error:
        join(db, access, 2)
    assert error.value.code == "chat_language_mismatch"
    assert db.repos[0].get(access.chat.id).status == "waiting"
    with db.engine.connect() as c:
        active = c.execute(select(language_profiles.c.id).where(
            language_profiles.c.user_id == db.people[2].id,
            language_profiles.c.is_active.is_(True),
        )).scalar_one()
    assert active == db.profiles[2].id


def test_create_and_join_replays_do_not_allocate_a_third_seat_or_return_used_token(db):
    request = ChatCreate(command_id=uuid4(), language_profile_id=db.profiles[0].id)
    access = db.repos[0].create(request)
    replay = db.repos[0].create(request)
    assert replay.chat == access.chat and replay.invite_token == ""
    with db.engine.connect() as c:
        stored = dict(c.execute(select(chats).where(
            chats.c.id == access.chat.id,
        )).mappings().one())
    assert access.invite_token not in str(stored)
    join_request = ChatJoin(command_id=uuid4(), language_profile_id=db.profiles[1].id,
        invite_token=access.invite_token)
    guest = db.repos[1].join(join_request)
    assert db.repos[1].join(join_request) == guest
    assert db.repos[0].create(request).invite_token == ""
    assert count(db, chats, chats.c.id == access.chat.id) == 1
    preview = db.repos[3].preview(access.invite_token).model_dump(by_alias=True, exclude_none=True)
    assert preview == {"status": "full"}
    with pytest.raises(RoomError) as error:
        join(db, access, 3)
    assert error.value.code == "chat_full"
    assert "tester" not in error.value.message
    with pytest.raises(RoomError) as error:
        db.repos[3].get(access.chat.id)
    assert error.value.status_code == 404


def test_rotation_revocation_and_expiry_prevent_old_invitation_access(db):
    access = create(db)
    rotated = db.repos[0].rotate_invite(access.chat.id, command(access.chat))
    assert rotated.invite_token != access.invite_token
    with pytest.raises(RoomError):
        db.repos[1].preview(access.invite_token)
    revoked = db.repos[0].revoke_invite(access.chat.id, command(rotated.chat))
    assert revoked.invite_status == "revoked"
    assert db.repos[1].preview(rotated.invite_token).status == "revoked"
    with pytest.raises(RoomError):
        join(db, rotated)
    renewed = db.repos[0].rotate_invite(access.chat.id, command(revoked))
    with db.engine.begin() as c:
        c.execute(update(chats).where(chats.c.id == access.chat.id).values(
            invite_expires_at=utc_now() - timedelta(seconds=1)))
    assert db.repos[1].preview(renewed.invite_token).status == "expired"
    with pytest.raises(RoomError) as error:
        join(db, renewed)
    assert error.value.code == "chat_invite_expired"


def test_two_concurrent_invitees_allocate_exactly_one_partner(db):
    access = create(db)
    def attempt(actor):
        try:
            return join(db, access, actor)
        except RoomError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [1, 3]))
    assert sum(not isinstance(result, RoomError) for result in results) == 1
    assert [result.code for result in results if isinstance(result, RoomError)] == ["chat_full"]
    assert db.repos[0].get(access.chat.id).partner.id in {db.people[1].id, db.people[3].id}


def test_only_owned_uploads_can_start_rounds_and_only_after_join(db):
    access = create(db)
    with pytest.raises(RoomError) as error:
        start(db, access.chat.id)
    assert error.value.code == "chat_waiting"
    join(db, access)
    snapshot = db.repos[0].get(access.chat.id)
    with pytest.raises(RoomError) as error:
        db.repos[0].start_round(access.chat.id, command(snapshot, StartChatRound,
            media_asset_id=db.assets[1][0].id))
    assert error.value.code == "chat_photo_invalid"
    assert db.repos[0].get(access.chat.id).active_round is None


def test_concurrent_round_starts_keep_one_active_round_and_replays_are_safe(db):
    access = paired(db)
    before = db.repos[0].get(access.chat.id)
    requests = [command(before, StartChatRound, media_asset_id=db.assets[actor][0].id)
        for actor in [0, 1]]
    def attempt(actor):
        try:
            return db.repos[actor].start_round(access.chat.id, requests[actor])
        except RoomError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [0, 1]))
    winners = [index for index, result in enumerate(results) if not isinstance(result, RoomError)]
    assert len(winners) == 1
    actor = winners[0]
    first = results[actor]
    assert db.repos[actor].start_round(access.chat.id, requests[actor]) == first
    assert count(db, rounds, rounds.c.chat_id == access.chat.id) == 1
    with pytest.raises(RoomError) as error:
        start(db, access.chat.id, 1 - actor)
    assert error.value.code == "chat_round_active"


def test_receiver_never_gets_unrevealed_object_inventory_or_private_content(db):
    access = paired(db)
    snapshot, target, _options = prepared(db, access.chat.id)
    round_id = snapshot.active_round.id
    sender = snapshot.active_round.model_dump(by_alias=True)
    assert sender["target"]["key"] == target["key"]
    assert "privateProviderContext" not in str(sender)
    guest = db.repos[1].get(access.chat.id).active_round.model_dump(by_alias=True)
    assert guest["target"] is None and guest["objects"] == [] and guest["clueOptions"] == []
    assert guest["imageUrl"] is None
    assert target["key"] not in str(guest) and target["word"] not in str(guest)
    with pytest.raises(RoomError):
        db.repos[1].image_asset(access.chat.id, round_id)
    sent = db.repos[0].send_clue(access.chat.id, round_id,
        command(snapshot, SendChatClue, text="Es pequeña."), "Es pequeña.")
    guest = db.repos[1].get(access.chat.id).active_round.model_dump(by_alias=True)
    assert guest["imageUrl"].startswith("/api/v1/friend-chats/")
    assert guest["target"] is None and guest["objects"] == [] and guest["clueOptions"] == []
    assert target["word"] not in str(guest) and target["key"] not in str(guest)
    assert db.repos[1].image_asset(access.chat.id, round_id).id == db.assets[0][0].id
    with pytest.raises(RoomError):
        db.repos[3].image_asset(access.chat.id, sent.active_round.id)


def test_custom_object_is_proposed_before_confirmation_and_not_shared(db):
    access = paired(db)
    snapshot = start(db, access.chat.id)
    round_id = snapshot.active_round.id
    job = db.repos[0].claim_photo(access.chat.id, round_id)
    content, _target, options = photo_content()
    db.repos[0].finish_photo(job, content=content)
    target = {"key": str(uuid4()), "label": "book", "word": "el libro",
        "translation": "the book", "x": .5, "y": .5, "width": .2, "height": .2}
    snapshot = db.repos[0].get(access.chat.id)
    proposal = db.repos[0].select_target(access.chat.id, round_id,
        command(snapshot, SelectChatTarget, x=.5, y=.5, confirm=False), target, [])
    assert proposal.active_round.status == "selectingTarget"
    assert proposal.active_round.target.key == target["key"]
    assert proposal.active_round.clue_options == []
    assert db.repos[1].get(access.chat.id).active_round.target is None
    with pytest.raises(RoomError):
        db.repos[0].send_clue(access.chat.id, round_id,
            command(proposal, SendChatClue, text="Es pequeño."), "Es pequeño.")
    confirmed = db.repos[0].select_target(access.chat.id, round_id,
        command(proposal, SelectChatTarget, object_key=target["key"], confirm=True),
        target, options)
    assert confirmed.active_round.status == "composingClue"


def test_wrong_coordinate_guess_keeps_target_private_until_followup_or_reveal(db):
    access = paired(db)
    snapshot, target, _options = awaiting_guess(db, access.chat.id)
    round_id = snapshot.active_round.id
    wrong = db.repos[1].guess(access.chat.id, round_id,
        command(snapshot, GuessChatTarget, x=.9, y=.9))
    assert wrong.active_round.status == "awaitingFollowUp"
    assert wrong.active_round.target is None and wrong.active_round.objects == []
    assert [message.type for message in wrong.active_round.messages] == [
        "clue", "guess", "incorrectResult",
    ]
    assert wrong.active_round.messages[1].x == .9
    with pytest.raises(RoomError):
        db.repos[1].guess(access.chat.id, round_id,
            command(wrong, GuessChatTarget, x=.25, y=.4))
    again = db.repos[0].send_clue(access.chat.id, round_id,
        command(wrong, SendChatClue, text="Está sobre la mesa."), "Está sobre la mesa.")
    assert again.active_round.target.key == target["key"]
    assert again.active_round.messages[-1].type == "followUpClue"
    correct = db.repos[1].guess(access.chat.id, round_id,
        command(again, GuessChatTarget, x=.25, y=.4))
    assert correct.active_round is None and correct.rounds[-1].status == "completed"
    assert correct.rounds[-1].target.word == "la taza"


@pytest.mark.parametrize("x,y", [(.25, .4), (.15, .4), (.25, .55)])
def test_correctness_uses_the_stored_bounding_region_including_its_edges(db, x, y):
    access = paired(db)
    snapshot, _target, _options = awaiting_guess(db, access.chat.id)
    completed = db.repos[1].guess(access.chat.id, snapshot.active_round.id,
        command(snapshot, GuessChatTarget, x=x, y=y))
    assert completed.active_round is None
    assert completed.rounds[-1].messages[-1].is_correct is True


def test_completed_history_survives_new_rounds_from_either_member_without_turn_order(db):
    access = paired(db)
    first, _target, _options = awaiting_guess(db, access.chat.id)
    first_round = first.active_round.id
    complete = db.repos[1].guess(access.chat.id, first_round,
        command(first, GuessChatTarget, x=.25, y=.4))
    next_round = start(db, access.chat.id, 0)
    assert next_round.rounds[0].id == first_round
    assert next_round.rounds[0].target.word == "la taza"
    assert next_round.active_round.sender_id == db.people[0].id
    cancelled = db.repos[0].finish_round(access.chat.id, next_round.active_round.id,
        command(next_round))
    guest_round = start(db, access.chat.id, 1)
    assert guest_round.active_round.sender_id == db.people[1].id
    assert len(guest_round.rounds) == 2
    restored = PostgresFriendChatRepository(db.engine, db.people[1].id).get(access.chat.id)
    assert restored.rounds[0] == complete.rounds[0]
    assert restored.rounds[1].status == "cancelled"
    assert cancelled.active_round is None


def test_replayed_correct_guess_adds_one_result_and_reused_action_cannot_change_guess(db):
    access = paired(db)
    snapshot, _target, _options = awaiting_guess(db, access.chat.id)
    round_id = snapshot.active_round.id
    request = command(snapshot, GuessChatTarget, x=.25, y=.4)
    completed = db.repos[1].guess(access.chat.id, round_id, request)
    assert db.repos[1].guess(access.chat.id, round_id, request) == completed
    assert count(db, messages, (messages.c.round_id == round_id)
        & (messages.c.type == "correctResult")) == 1
    changed = request.model_copy(update={"x": .9})
    with pytest.raises(RoomError) as error:
        db.repos[1].guess(access.chat.id, round_id, changed)
    assert error.value.code == "chat_command_conflict"


def test_concurrent_correct_guesses_store_one_result(db):
    access = paired(db)
    snapshot, _target, _options = awaiting_guess(db, access.chat.id)
    round_id = snapshot.active_round.id
    requests = [command(snapshot, GuessChatTarget, x=.25, y=.4) for _ in range(2)]

    def attempt(request):
        try:
            return db.repos[1].guess(access.chat.id, round_id, request)
        except RoomError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, requests))
    assert sum(not isinstance(result, RoomError) for result in results) == 1
    assert count(db, messages, (messages.c.round_id == round_id)
        & (messages.c.type == "correctResult")) == 1
    assert count(db, messages, (messages.c.round_id == round_id)
        & (messages.c.type == "guess")) == 1


def test_profile_changes_do_not_change_an_existing_chats_language_or_viewer_level(db):
    access = paired(db)
    PostgresLanguageProfileRepository(db.engine).create(LanguageProfile(
        user_id=db.people[0].id, source_language_code="en", target_language_code="fr",
        proficiency_level="A2",
    ))
    snapshot = db.repos[0].get(access.chat.id)
    assert snapshot.viewer_level == "A0" and snapshot.target_language_code == "es"
    started = start(db, access.chat.id)
    job = db.repos[0].claim_photo(access.chat.id, started.active_round.id)
    assert job.profile["id"] == str(db.profiles[0].id)
    assert job.profile["target_language_code"] == "es"
    assert job.profile["proficiency_level"] == "A0"


def test_suggestion_and_private_help_do_not_change_the_shared_snapshot(db):
    access = paired(db)
    snapshot, _target, _options = prepared(db, access.chat.id)
    round_id = snapshot.active_round.id
    request = command(snapshot)
    assert db.repos[0].suggestion(access.chat.id, round_id, request, "Es pequeña.") == {
        "text": "Es pequeña.",
    }
    assert db.repos[0].suggestion(access.chat.id, round_id, request, "Other output") == {
        "text": "Es pequeña.",
    }
    assert db.repos[0].get(access.chat.id) == snapshot
    snapshot = db.repos[0].send_clue(access.chat.id, round_id,
        command(snapshot, SendChatClue, text="Es pequeña."), "Es pequeña.")
    before = db.repos[0].get(access.chat.id)
    db.repos[1].record_help(access.chat.id, round_id)
    db.repos[1].record_help(access.chat.id, round_id)
    assert db.repos[0].get(access.chat.id) == before
    assert count(db, assistance, assistance.c.round_id == round_id) == 2
    with pytest.raises(RoomError):
        db.repos[0].record_help(access.chat.id, round_id)
    with pytest.raises(RoomError):
        db.repos[3].record_help(access.chat.id, round_id)


def test_report_reason_stays_private_and_replay_creates_one_report(db):
    access = paired(db)
    before = db.repos[1].get(access.chat.id)
    request = command(before, ReportChat, reason="Inappropriate photo sent to me")
    db.repos[0].report(access.chat.id, request)
    db.repos[0].report(access.chat.id, request)
    assert db.repos[1].get(access.chat.id) == before
    assert count(db, reports, reports.c.chat_id == access.chat.id) == 1
    assert request.reason not in str(before.model_dump(by_alias=True))


def test_block_closes_all_existing_pair_chats_and_prevents_new_pair_joins(db):
    first = paired(db)
    second = create(db)
    join(db, second)
    ready, _target, _options = awaiting_guess(db, first.chat.id)
    round_id = ready.active_round.id
    db.repos[1].close(first.chat.id, command(ready), block=True)
    assert db.repos[0].get(first.chat.id).status == "blocked"
    assert db.repos[0].get(second.chat.id).status == "blocked"
    assert count(db, blocks, blocks.c.user_id == db.people[1].id) == 1
    with pytest.raises(RoomError):
        db.repos[0].image_asset(first.chat.id, round_id)
    with pytest.raises(RoomError):
        start(db, first.chat.id)
    fresh = create(db)
    assert db.repos[1].preview(fresh.invite_token).status == "revoked"
    with pytest.raises(RoomError) as error:
        join(db, fresh)
    assert error.value.code == "chat_invite_revoked"


def test_stale_photo_job_cannot_publish_after_leave_or_cancellation(db):
    access = paired(db)
    snapshot = start(db, access.chat.id)
    round_id = snapshot.active_round.id
    job = db.repos[0].claim_photo(access.chat.id, round_id)
    assert job is not None
    closed = db.repos[1].close(access.chat.id, command(snapshot))
    content, _target, _options = photo_content()
    db.repos[0].finish_photo(job, content=content)
    restored = db.repos[0].get(access.chat.id)
    assert restored.status == "left" and restored.active_round is None
    assert restored.revision == closed.revision
    assert restored.rounds[-1].status == "cancelled"
    assert restored.rounds[-1].objects == [] and restored.rounds[-1].target is None
    assert restored.rounds[-1].image_url is None
    with pytest.raises(RoomError):
        db.repos[0].image_asset(access.chat.id, round_id)


def test_photo_failure_can_retry_but_an_expired_claim_cannot_overwrite_new_analysis(db):
    access = paired(db)
    snapshot = start(db, access.chat.id)
    round_id = snapshot.active_round.id
    first_job = db.repos[0].claim_photo(access.chat.id, round_id)
    db.repos[0].finish_photo(first_job, error="Photo analysis did not finish. Try again.")
    failed = db.repos[0].get(access.chat.id)
    assert failed.active_round.photo_status == "failed" and failed.active_round.retryable
    db.repos[0].retry(access.chat.id, round_id, command(failed))
    second_job = db.repos[0].claim_photo(access.chat.id, round_id)
    assert second_job.claim_id != first_job.claim_id
    content, _target, _options = photo_content()
    db.repos[0].finish_photo(first_job, content=content)
    assert db.repos[0].get(access.chat.id).active_round.photo_status == "analyzing"
    db.repos[0].finish_photo(second_job, content=content)
    assert db.repos[0].get(access.chat.id).active_round.photo_status == "ready"


def test_nonretryable_photo_rejection_cannot_start_another_analysis_attempt(db):
    access = paired(db)
    snapshot = start(db, access.chat.id)
    round_id = snapshot.active_round.id
    job = db.repos[0].claim_photo(access.chat.id, round_id)
    db.repos[0].finish_photo(job, error="Choose another photo.", retryable=False)
    rejected = db.repos[0].get(access.chat.id)
    assert rejected.active_round.photo_status == "failed"
    assert rejected.active_round.error == "Choose another photo."
    assert rejected.active_round.retryable is False
    with pytest.raises(RoomError) as error:
        db.repos[0].retry(access.chat.id, round_id, command(rejected))
    assert error.value.code == "chat_retry_unavailable"
    assert db.repos[0].get(access.chat.id) == rejected
    with db.engine.connect() as c:
        stored = c.execute(select(rounds.c.analysis_attempts, rounds.c.retryable)
            .where(rounds.c.id == round_id)).mappings().one()
    assert stored["analysis_attempts"] == 1 and stored["retryable"] is False


def test_explicit_reveal_and_cancel_are_sender_only_and_cancel_keeps_answer_hidden(db):
    access = paired(db)
    snapshot, target, _options = awaiting_guess(db, access.chat.id)
    round_id = snapshot.active_round.id
    with pytest.raises(RoomError):
        db.repos[1].finish_round(access.chat.id, round_id, command(snapshot), reveal=True)
    revealed = db.repos[0].finish_round(access.chat.id, round_id, command(snapshot), reveal=True)
    assert revealed.rounds[-1].messages[-1].type == "reveal"
    assert target["word"] in revealed.rounds[-1].messages[-1].text
    next_round, _target, _options = prepared(db, access.chat.id)
    db.repos[0].finish_round(access.chat.id, next_round.active_round.id, command(next_round))
    guest = db.repos[1].get(access.chat.id)
    assert guest.rounds[-1].status == "cancelled"
    assert guest.rounds[-1].target is None and guest.rounds[-1].objects == []


def test_account_deletion_cascades_private_chat_history_and_rejects_inflight_jobs(db):
    access = paired(db)
    snapshot = start(db, access.chat.id)
    job = db.repos[0].claim_photo(access.chat.id, snapshot.active_round.id)
    with db.engine.begin() as c:
        c.execute(delete(media_assets).where(media_assets.c.owner_user_id == db.people[0].id))
        c.execute(delete(users).where(users.c.id == db.people[0].id))
    assert count(db, chats, chats.c.id == access.chat.id) == 0
    assert count(db, rounds, rounds.c.chat_id == access.chat.id) == 0
    assert count(db, messages, messages.c.chat_id == access.chat.id) == 0
    with pytest.raises(RoomError):
        db.repos[1].get(access.chat.id)
    with pytest.raises(RoomError):
        db.repos[0].finish_photo(job, content=photo_content()[0])


class PreparedContent:
    """Deterministic photo content; authorization and state use the real repository."""

    def __init__(self):
        self.content, self.target, self.options = photo_content()
        self.selections = self.validations = self.suggestions = 0

    def analyze(self, _round_id, _owner_id, _asset, _profile):
        return self.content

    def select_target(self, content, *, object_key, **_kwargs):
        self.selections += 1
        return next(obj for obj in content["objects"] if obj["key"] == object_key)

    def clue_options(self, _content, _target, _profile):
        return self.options

    def validate_clue(self, text, _target, _content, _profile, **_kwargs):
        self.validations += 1
        return text

    def suggest_clue(self, _content, _target, _profile):
        self.suggestions += 1
        return "Es pequeña."


def test_service_preserves_nonretryable_photo_failures(db):
    from app.services.friend_chats import FriendChatService
    from app.services.room_photos import RoomPhotoError

    access = paired(db)

    def rejected_photo(*_args):
        raise RoomPhotoError("chat_photo_rejected", "Choose another photo.", retryable=False)

    service = FriendChatService(db.repos[0], SimpleNamespace(analyze=rejected_photo))
    before = db.repos[0].get(access.chat.id)
    rejected = service.start_round(access.chat.id, command(before, StartChatRound,
        media_asset_id=db.assets[0][0].id))
    assert rejected.active_round.photo_status == "failed"
    assert rejected.active_round.error == "Choose another photo."
    assert rejected.active_round.retryable is False
    with pytest.raises(RoomError) as error:
        service.retry(access.chat.id, rejected.active_round.id, command(rejected))
    assert error.value.code == "chat_retry_unavailable"


def test_service_replays_do_not_repeat_model_work_after_round_completion(db):
    from app.services.friend_chats import FriendChatService

    access = paired(db)
    content = PreparedContent()
    service = FriendChatService(db.repos[0], content)
    before = db.repos[0].get(access.chat.id)
    ready = service.start_round(access.chat.id, command(before, StartChatRound,
        media_asset_id=db.assets[0][0].id))
    round_id = ready.active_round.id
    target_request = command(ready, SelectChatTarget,
        object_key=content.target["key"], confirm=True)
    composing = service.select_target(access.chat.id, round_id, target_request)
    suggestion_request = command(composing)
    assert service.suggest(access.chat.id, round_id, suggestion_request).text == "Es pequeña."
    clue_request = command(composing, SendChatClue, text="Es pequeña.")
    clue = service.clue(access.chat.id, round_id, clue_request)
    completed = db.repos[1].guess(access.chat.id, round_id,
        command(clue, GuessChatTarget, x=.25, y=.4))
    assert completed.active_round is None
    assert service.clue(access.chat.id, round_id, clue_request).active_round is None
    assert service.select_target(access.chat.id, round_id, target_request).active_round is None
    assert service.suggest(access.chat.id, round_id, suggestion_request).text == "Es pequeña."
    assert (content.selections, content.validations, content.suggestions) == (1, 1, 1)


def test_model_result_cannot_publish_when_partner_leaves_during_selection(db):
    from app.services.friend_chats import FriendChatService

    access = paired(db)
    content = PreparedContent()
    service = FriendChatService(db.repos[0], content)
    before = db.repos[0].get(access.chat.id)
    ready = service.start_round(access.chat.id, command(before, StartChatRound,
        media_asset_id=db.assets[0][0].id))
    round_id = ready.active_round.id
    original = content.select_target

    def selection_after_leave(*args, **kwargs):
        current = db.repos[1].get(access.chat.id)
        db.repos[1].close(access.chat.id, command(current))
        return original(*args, **kwargs)

    content.select_target = selection_after_leave
    with pytest.raises(RoomError) as error:
        service.select_target(access.chat.id, round_id,
            command(ready, SelectChatTarget, object_key=content.target["key"], confirm=True))
    assert error.value.code == "chat_closed"
    assert db.repos[0].get(access.chat.id).rounds[-1].target is None


def test_api_uses_authenticated_actor_and_private_image_response_headers(db):
    from typing import Annotated
    from uuid import UUID

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_friend_chat_service
    from app.api.routes.friend_chats import router
    from app.services.friend_chats import FriendChatService

    app = FastAPI()

    def service(actor: Annotated[str | None, Header(alias="X-Test-Actor")] = None):
        if actor is None:
            raise HTTPException(401, detail="Sign in")
        return FriendChatService(PostgresFriendChatRepository(db.engine, UUID(actor)),
            PreparedContent(), image_reader=lambda _asset, _width: b"private-webp")

    app.dependency_overrides[get_friend_chat_service] = service
    app.include_router(router, prefix="/api/v1")
    access = paired(db)
    snapshot, _target, _options = awaiting_guess(db, access.chat.id)
    round_id = snapshot.active_round.id
    path = f"/api/v1/friend-chats/{access.chat.id}/rounds/{round_id}/image?width=640"
    with TestClient(app) as client:
        assert client.get("/api/v1/friend-chats").status_code == 401
        assert client.get(path).status_code == 401
        outsider = {"X-Test-Actor": str(db.people[3].id)}
        assert client.get(path, headers=outsider).status_code == 404
        full = client.post("/api/v1/friend-chats/invites/preview",
            json={"inviteToken": access.invite_token}, headers=outsider)
        assert full.status_code == 200 and full.json() == {"status": "full"}
        image = client.get(path, headers={"X-Test-Actor": str(db.people[1].id)})
        assert image.status_code == 200 and image.content == b"private-webp"
        assert image.headers["cache-control"] == "private, no-store"
        assert image.headers["vary"] == "Authorization"
        invalid_width = client.get(path.replace("width=640", "width=100000"),
            headers={"X-Test-Actor": str(db.people[1].id)})
        assert invalid_width.status_code == 422


def test_chat_tables_enable_rls_and_grant_no_public_table_access(db):
    names = [table.name for table in [chats, rounds, messages, reports, blocks, assistance]]
    schema = os.getenv("TEST_DATABASE_SCHEMA", "public")
    with db.engine.connect() as c:
        rows = c.execute(text("""
            SELECT relation.relname, relation.relrowsecurity,
                   EXISTS (
                       SELECT 1
                       FROM aclexplode(COALESCE(relation.relacl,
                           acldefault('r', relation.relowner))) AS privilege
                       WHERE privilege.grantee = 0
                   ) AS public_access
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = :schema AND relation.relname = ANY(:names)
        """), {"schema": schema, "names": names}).mappings().all()
    assert len(rows) == len(names)
    assert all(row["relrowsecurity"] and not row["public_access"] for row in rows)
