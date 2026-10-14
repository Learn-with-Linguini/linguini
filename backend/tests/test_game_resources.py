"""Resource balances and solo lessons share an atomic, account-scoped ledger."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, update

from app.database import create_database_engine
from app.main import create_app
from app.repositories.postgres.game_resources import (
    GameResourcesUnavailableError,
    InsufficientBasilError,
    ResourceCommandConflictError,
    SauceExhaustedError,
    equip_appearance,
    game_accounts,
    game_resource_events,
    lock_resource_owner,
    refund_sauce,
    resource_snapshot,
    reward_basil,
    sauce_capacity,
    spend_sauce,
)
from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.users import users
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.base import utc_now
from app.schemas.media import MediaAsset
from app.schemas.sessions import CreateSessionRequest
from app.schemas.users import LanguageProfile, User
from app.services.background import InlineBackgroundRunner


@pytest.fixture
def resources(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.delenv("GAME_RESOURCES_ENABLED", raising=False)
    monkeypatch.setenv("DAILY_SAUCE_CAPACITY", "10")
    monkeypatch.setenv("MEDIA_STORAGE_PRIVATE", "false")
    engine = create_database_engine()
    owner = User(display_name="Sauce learner", auth_provider_id=f"resource-{uuid4()}")
    other = User(display_name="Other learner", auth_provider_id=f"resource-{uuid4()}")
    monkeypatch.setenv("DEMO_USER_ID", str(owner.id))
    with engine.begin() as c:
        c.execute(insert(users), [u.model_dump(by_alias=False) for u in (owner, other)])
    profile = PostgresLanguageProfileRepository(engine).create(LanguageProfile(
        user_id=owner.id, source_language_code="en", target_language_code="es",
        proficiency_level="A1",
    ))
    asset = MediaAsset(owner_user_id=owner.id, source="userUpload", media_type="image",
                       storage_key=f"users/{owner.id}/images/{uuid4()}.jpg", mime_type="image/jpeg")
    with engine.begin() as c:
        c.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
    with TestClient(create_app()) as client:
        client.app.state.background_runner = InlineBackgroundRunner()
        yield engine, owner, other, profile, asset, client
    with engine.begin() as c:
        c.execute(delete(sessions).where(sessions.c.user_id.in_([owner.id, other.id])))
        c.execute(delete(media_assets).where(media_assets.c.id == asset.id))
        c.execute(delete(users).where(users.c.id.in_([owner.id, other.id])))
    engine.dispose()


def atomic(engine, owner, fn, *args):
    with engine.begin() as c:
        lock_resource_owner(c, owner.id)
        return fn(c, owner.id, *args)


def balance(engine, owner):
    return atomic(engine, owner, resource_snapshot)


def create_solo(client, profile, asset, key="solo-request-1"):
    return client.post("/api/v1/sessions", json={
        "languageProfileId": str(profile.id), "mediaAssetId": str(asset.id),
        "idempotencyKey": key,
    })


def test_charge_and_reward_replays_are_account_scoped(resources):
    engine, owner, other, *_ = resources
    assert atomic(engine, owner, spend_sauce, "lesson:1") == 1
    assert atomic(engine, owner, spend_sauce, "lesson:1") == 0
    assert atomic(engine, owner, reward_basil, "task:1") == 1
    assert atomic(engine, owner, reward_basil, "task:1") == 0
    assert balance(engine, owner).sauce.remaining == 9

    assert balance(engine, owner).basil_leaves == 1
    assert balance(engine, other).sauce.remaining == 10
    assert balance(engine, other).basil_leaves == 0


def test_parallel_starts_cannot_overspend_or_repeat(resources, monkeypatch):
    engine, owner, *_ = resources
    monkeypatch.setenv("DAILY_SAUCE_CAPACITY", "1")

    def start(key):
        try:
            return atomic(engine, owner, spend_sauce, key)
        except SauceExhaustedError:
            return "empty"

    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(start, ["one", "one", "two", "three"]))
    assert result.count(1) == 1
    assert balance(engine, owner).sauce.remaining == 0
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(game_resource_events).where(
            game_resource_events.c.user_id == owner.id,
        )).scalar_one() == 1


def test_refund_is_once_even_if_legacy_feature_flag_is_false(resources, monkeypatch):
    engine, owner, *_ = resources
    assert atomic(engine, owner, spend_sauce, "setup") == 1
    monkeypatch.setenv("GAME_RESOURCES_ENABLED", "false")
    assert atomic(engine, owner, refund_sauce, "setup") == 1
    assert atomic(engine, owner, refund_sauce, "setup") == 0
    assert balance(engine, owner).sauce.remaining == 10


def test_refund_without_charge_does_not_initialize_resources(resources):
    engine, owner, *_ = resources
    assert atomic(engine, owner, refund_sauce, "never-started") == 0
    with engine.connect() as c:
        assert not c.execute(select(game_accounts).where(
            game_accounts.c.user_id == owner.id,
        )).first()
        assert not c.execute(select(game_resource_events).where(
            game_resource_events.c.user_id == owner.id,
        )).first()


def test_old_refund_cannot_refill_new_period(resources, monkeypatch):
    engine, owner, *_ = resources
    atomic(engine, owner, spend_sauce, "yesterday")
    now = utc_now() + timedelta(days=1)
    monkeypatch.setattr("app.repositories.postgres.game_resources.utc_now", lambda: now)
    atomic(engine, owner, spend_sauce, "today")
    atomic(engine, owner, refund_sauce, "yesterday")
    assert balance(engine, owner).sauce.remaining == 9
    assert balance(engine, owner).sauce.refills_at > now


def test_parallel_basil_reward_and_appearance_purchases(resources):
    engine, owner, *_ = resources
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: atomic(engine, owner, reward_basil, "same"), range(8))) == 1
    for i in range(19):
        atomic(engine, owner, reward_basil, f"task:{i}")

    def equip(appearance):
        try:
            return atomic(engine, owner, equip_appearance, appearance, uuid4()).appearance
        except InsufficientBasilError:
            return "insufficient"

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(equip, ["herb", "pasta"]))
    assert result.count("insufficient") == 1
    state = balance(engine, owner)
    assert state.basil_leaves == 0
    assert len(state.owned_appearances) == 2
    assert state.appearance in state.owned_appearances
    assert atomic(engine, owner, equip_appearance, "default", uuid4()).basil_leaves == 0
    assert atomic(engine, owner, equip_appearance, state.appearance, uuid4()).basil_leaves == 0


def test_appearance_command_replay_does_not_reequip_or_accept_changed_payload(resources):
    engine, owner, *_ = resources
    for i in range(20):
        atomic(engine, owner, reward_basil, f"task:{i}")
    command = uuid4()
    atomic(engine, owner, equip_appearance, "herb", command)
    atomic(engine, owner, equip_appearance, "default", uuid4())
    assert atomic(engine, owner, equip_appearance, "herb", command).appearance == "default"
    with pytest.raises(ResourceCommandConflictError):
        atomic(engine, owner, equip_appearance, "pasta", command)


@pytest.mark.parametrize("legacy_flag", [None, "false"])
def test_resources_are_automatic_without_feature_switch(resources, monkeypatch, legacy_flag):
    engine, owner, _, profile, asset, client = resources
    if legacy_flag is not None:
        monkeypatch.setenv("GAME_RESOURCES_ENABLED", legacy_flag)
    response = client.get("/api/v1/me/game-resources")
    assert response.status_code == 200, response.text
    assert response.json()["sauce"]["remaining"] == 10
    response = create_solo(client, profile, asset)
    assert response.status_code == 202, response.text
    sid = response.json()["session"]["id"]
    assert balance(engine, owner).sauce.remaining == 9
    assert atomic(engine, owner, reward_basil, "submitted-task") == 1
    assert client.post(f"/api/v1/sessions/{sid}/abandon").status_code == 200
    state = client.get("/api/v1/me/game-resources").json()
    assert state["sauce"]["remaining"] == 10
    assert state["basilLeaves"] == 1
    with engine.connect() as c:
        events = c.execute(select(game_resource_events.c.kind).where(
            game_resource_events.c.user_id == owner.id,
        )).scalars().all()
    assert sorted(events) == ["basilEarned", "sauceRefund", "sauceSpend"]


def test_beta_uses_sauce_and_empty_start_is_atomic(resources, monkeypatch):
    engine, owner, _, profile, asset, client = resources
    monkeypatch.setenv("DAILY_SAUCE_CAPACITY", "1")
    with engine.begin() as c:
        c.execute(update(users).where(users.c.id == owner.id).values(tier="beta"))
    atomic(engine, owner, spend_sauce, "prior")
    response = create_solo(client, profile, asset)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "sauce_empty"
    with engine.connect() as c:
        assert not c.execute(select(sessions.c.id).where(sessions.c.user_id == owner.id)).first()


def test_solo_resume_and_replayed_abandon_do_not_repeat_charge_or_refund(resources):
    engine, owner, _, profile, asset, client = resources
    first = create_solo(client, profile, asset)
    assert first.status_code == 202, first.text
    sid = first.json()["session"]["id"]
    assert create_solo(client, profile, asset).json()["session"]["id"] == sid
    assert create_solo(client, profile, asset, "different-key").json()["session"]["id"] == sid
    assert balance(engine, owner).sauce.remaining == 9
    assert client.post(f"/api/v1/sessions/{sid}/abandon").status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/abandon").status_code == 200
    assert balance(engine, owner).sauce.remaining == 10


def test_crashed_analysis_refunds_before_retry_charges_once(resources):
    engine, owner, _, profile, asset, client = resources
    response = create_solo(client, profile, asset)
    sid = UUID(response.json()["session"]["id"])
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.id == sid).values(
            status="analyzingScene", analysis_draft={
                "analysisAttempts": 1,
                "processingStartedAt": (utc_now() - timedelta(minutes=20)).isoformat(),
            },
        ))
    detail = client.get(f"/api/v1/sessions/{sid}")
    assert detail.json()["session"]["status"] == "failed", detail.text
    assert balance(engine, owner).sauce.remaining == 10
    for _ in range(2):
        retry = client.post(f"/api/v1/sessions/{sid}/retry-analysis")
        assert retry.status_code == 200, retry.text
    assert balance(engine, owner).sauce.remaining == 9
    assert client.post(f"/api/v1/sessions/{sid}/abandon").status_code == 200
    assert balance(engine, owner).sauce.remaining == 10


def test_basil_only_rewards_submitted_practice_not_skip_or_reading(resources):
    engine, owner, _, profile, _, client = resources
    scene = next(s for s in client.get("/api/v1/preloaded-scenes").json()
                 if s["languageCode"] == "es")
    response = create_solo(client, profile, SimpleNamespace(id=scene["mediaAsset"]["id"]))
    sid = response.json()["session"]["id"]
    assert client.post(f"/api/v1/sessions/{sid}/analyze").status_code == 200
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    assert client.put(f"/api/v1/sessions/{sid}/review", json={
        "acceptedObjectIds": [detail["sceneObjects"][0]["id"]],
    }).status_code == 200
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    intro = detail["tasks"][0]
    answers = {q["questionId"]: q["options"][0]["optionId"]
               for q in intro["publicContent"]["questions"]}
    payload = {"inputMode": "vocabularyReview", "answers": answers, "idempotencyKey": "vocab-once"}
    for _ in range(2):
        answer = client.post(f"/api/v1/tasks/{intro['id']}/attempts", json=payload)
        assert answer.status_code == 200, answer.text
    assert balance(engine, owner).basil_leaves == 1
    for task in detail["tasks"][1:]:
        if task["kind"] in {"grammarExplanation", "syntaxExplanation"}:
            action = client.post(f"/api/v1/tasks/{task['id']}/complete")
        else:
            action = client.post(f"/api/v1/tasks/{task['id']}/skip", json={"reason": "later"})
        assert action.status_code == 200, action.text
    assert balance(engine, owner).basil_leaves == 1


def test_resources_api_rejects_invalid_appearance_and_insufficient_funds(resources):
    *_, client = resources
    assert client.get("/api/v1/me/game-resources").json()["sauce"]["capacity"] == 10
    response = client.post("/api/v1/me/game-resources/appearance", json={
        "appearance": "herb", "commandId": str(uuid4()),
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "insufficient_basil"
    assert client.post("/api/v1/me/game-resources/appearance", json={
        "appearance": "unlisted", "commandId": str(uuid4()),
    }).status_code == 422


@pytest.mark.parametrize("legacy_flag,private,status", [
    (None, "false", 503),
    ("false", "false", 503),
    (None, "true", 200),
    ("false", "true", 200),
])
def test_rooms_require_private_storage_without_feature_switch(
    resources, monkeypatch, legacy_flag, private, status,
):
    *_, client = resources
    monkeypatch.delenv("PLAY_TOGETHER_ENABLED", raising=False)
    if legacy_flag is not None:
        monkeypatch.setenv("PLAY_TOGETHER_ENABLED", legacy_flag)
    monkeypatch.setenv("MEDIA_STORAGE_PRIVATE", private)
    response = client.get("/api/v1/rooms/active")
    assert response.status_code == status, response.text


def test_new_solo_request_is_charged_in_the_same_transaction(resources):
    engine, owner, _, profile, asset, _ = resources
    repository = PostgresWorkflowRepository(engine, owner.id)
    request = CreateSessionRequest(language_profile_id=profile.id, media_asset_id=asset.id)
    detail = repository.create(request)
    assert balance(engine, owner).sauce.remaining == 9
    assert repository.create(request).session.id == detail.session.id
    assert balance(engine, owner).sauce.remaining == 9


@pytest.mark.parametrize("configured,expected", [(None, 10), ("1", 1), ("100", 100)])
def test_daily_sauce_default_and_capacity_bounds(monkeypatch, configured, expected):
    monkeypatch.delenv("DAILY_SAUCE_CAPACITY", raising=False)
    if configured is not None:
        monkeypatch.setenv("DAILY_SAUCE_CAPACITY", configured)
    assert sauce_capacity() == expected


@pytest.mark.parametrize("configured", ["0", "101", "ten", ""])
def test_invalid_daily_sauce_capacity_is_reported(monkeypatch, configured):
    monkeypatch.setenv("DAILY_SAUCE_CAPACITY", configured)
    with pytest.raises(GameResourcesUnavailableError):
        sauce_capacity()
