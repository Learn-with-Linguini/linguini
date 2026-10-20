"""Account deletion is authenticated, scoped, and irreversible."""

import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select

from app.api.auth import get_authenticated_identity
from app.api.dependencies import get_account_deletion_service, get_user_service
from app.database import create_database_engine
from app.main import create_app
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.users import PostgresUserRepository, users
from app.schemas.users import User
from app.services.account_deletion import AccountDeletionService
from app.services.auth import AuthenticatedIdentity
from app.services.image_storage import ImageStorage


def _client(user: User, identity: AuthenticatedIdentity | None, deletion: object):
    app = create_app()
    app.state.database_engine = None
    app.dependency_overrides[get_user_service] = lambda: SimpleNamespace(
        get_current_user=lambda: user
    )
    app.dependency_overrides[get_authenticated_identity] = lambda: identity
    app.dependency_overrides[get_account_deletion_service] = lambda: deletion
    return TestClient(app)


def test_delete_me_deletes_only_the_authenticated_account():
    user = User(auth_provider_id=str(uuid4()), display_name="Learner")
    deletion = Mock()
    identity = AuthenticatedIdentity(
        subject=user.auth_provider_id,
        email="learner@example.com",
        is_anonymous=False,
    )

    response = _client(user, identity, deletion).delete("/api/v1/me")

    assert response.status_code == 204
    deletion.delete_account.assert_called_once_with(user.id, user.auth_provider_id)


def test_delete_me_rejects_demo_auth():
    user = User(auth_provider_id=str(uuid4()), display_name="Learner")
    deletion = Mock()

    response = _client(user, None, deletion).delete("/api/v1/me")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_deletion_unavailable"
    deletion.delete_account.assert_not_called()


def test_storage_prefix_cleanup_deletes_only_listed_objects(monkeypatch):
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = [
        {"name": "one.webp", "id": "1"},
        {"name": "two.webp", "id": "2"},
    ]
    remove = Mock()
    remove.raise_for_status.return_value = None
    post = Mock(return_value=first)
    request = Mock(return_value=remove)
    monkeypatch.setattr("app.services.image_storage.httpx.post", post)
    monkeypatch.setattr("app.services.image_storage.httpx.request", request)
    storage = ImageStorage("https://project.supabase.co", "service-role-key")

    storage.delete_prefixes(["users/current-user/images"])

    assert post.call_args.kwargs["json"]["prefix"] == "users/current-user/images"
    assert request.call_args.kwargs["json"] == {
        "prefixes": [
            "users/current-user/images/one.webp",
            "users/current-user/images/two.webp",
        ]
    }


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires migrated test PostgreSQL")
def test_account_deletion_keeps_other_users_data(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    user = User(auth_provider_id=f"delete-{uuid4()}", display_name="Delete me")
    other = User(auth_provider_id=f"keep-{uuid4()}", display_name="Keep me")
    user_asset_id, other_asset_id = uuid4(), uuid4()
    user_profile_id, other_profile_id = uuid4(), uuid4()
    now = user.created_at
    storage = SimpleNamespace(configured=True, delete_prefixes=Mock())
    auth_admin = SimpleNamespace(configured=True, delete_user=Mock())
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(users),
                [user.model_dump(by_alias=False), other.model_dump(by_alias=False)],
            )
            connection.execute(
                insert(language_profiles),
                [
                    {
                        "id": user_profile_id,
                        "user_id": user.id,
                        "source_language_code": "en",
                        "target_language_code": "es",
                        "proficiency_level": "A1",
                        "is_active": True,
                        "preferred_input_mode": "both",
                        "daily_goal_minutes": 10,
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "id": other_profile_id,
                        "user_id": other.id,
                        "source_language_code": "en",
                        "target_language_code": "fr",
                        "proficiency_level": "A1",
                        "is_active": True,
                        "preferred_input_mode": "both",
                        "daily_goal_minutes": 10,
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            connection.execute(
                insert(media_assets),
                [
                    {
                        "id": user_asset_id,
                        "owner_user_id": user.id,
                        "media_type": "image",
                        "source": "userUpload",
                        "storage_key": f"users/{user.id}/photo.webp",
                        "mime_type": "image/webp",
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "id": other_asset_id,
                        "owner_user_id": other.id,
                        "media_type": "image",
                        "source": "userUpload",
                        "storage_key": f"users/{other.id}/photo.webp",
                        "mime_type": "image/webp",
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )

        AccountDeletionService(engine, storage, auth_admin).delete_account(
            user.id, user.auth_provider_id
        )

        assert PostgresUserRepository(engine).get_by_id(user.id) is None
        assert PostgresUserRepository(engine).get_by_id(other.id) == other
        with engine.connect() as connection:
            assert connection.execute(
                select(language_profiles.c.id).where(
                    language_profiles.c.user_id == other.id
                )
            ).scalar_one() == other_profile_id
            assert connection.execute(
                select(media_assets.c.id).where(media_assets.c.owner_user_id == other.id)
            ).scalar_one() == other_asset_id
        deleted_prefixes = storage.delete_prefixes.call_args.args[0]
        assert f"users/{user.id}/images" in deleted_prefixes
        assert f"derived/v2/w320/users/{user.id}/images" in deleted_prefixes
        assert all(str(other.id) not in prefix for prefix in deleted_prefixes)
        auth_admin.delete_user.assert_called_once_with(user.auth_provider_id)
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(language_profiles).where(
                    language_profiles.c.user_id.in_([user.id, other.id])
                )
            )
            connection.execute(
                delete(media_assets).where(
                    media_assets.c.owner_user_id.in_([user.id, other.id])
                )
            )
            connection.execute(delete(users).where(users.c.id.in_([user.id, other.id])))
        engine.dispose()
