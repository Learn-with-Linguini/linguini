"""Repository unit checks plus opt-in tests against an empty migrated test database."""

import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert
from sqlalchemy.exc import OperationalError

from app.database import create_database_engine
from app.main import create_app
from app.repositories.postgres.users import PostgresUserRepository, users
from app.repositories.users import UserRepositoryError
from app.schemas.users import UpdateUserRequest, User


@pytest.mark.parametrize("url", ["", "sqlite:///test.db", "not-a-url"])
def test_invalid_database_configuration(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_database_engine()


def test_database_errors_are_wrapped():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("select", {}, Exception("private detail"))
    engine.begin.side_effect = OperationalError("update", {}, Exception("private detail"))
    repository = PostgresUserRepository(engine)
    with pytest.raises(UserRepositoryError, match="Unable to load user"):
        repository.get_by_id(uuid4())
    with pytest.raises(UserRepositoryError, match="Unable to save user"):
        repository.update(uuid4(), UpdateUserRequest(display_name="Changed"))


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("postgresql://user:secret@localhost/db?pgbouncer=true", "Prisma-only"),
        ("postgresql://user:secret@aws-0-region.pooler.supabase.com:6543/db", "Session pooler"),
    ],
)
def test_incompatible_pooler_configuration(monkeypatch, url, message):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError, match=message) as error:
        create_database_engine()
    assert "secret" not in str(error.value)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires migrated test PostgreSQL")
def test_postgres_roundtrip_and_api(monkeypatch):
    # Use a dedicated database with the committed Prisma migration already applied.
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    user = User(
        auth_provider_id=f"test-{uuid4()}", display_name="Test User", timezone="Asia/Singapore"
    )
    monkeypatch.setenv("DEMO_USER_ID", str(user.id))
    engine = create_database_engine()
    try:
        with engine.begin() as connection:
            connection.execute(insert(users).values(**user.model_dump(by_alias=False)))
        repository = PostgresUserRepository(engine)
        assert repository.get_by_id(user.id) == user
        assert repository.get_by_id(uuid4()) is None
        assert repository.update(uuid4(), UpdateUserRequest(display_name="Absent")) is None
        with TestClient(create_app()) as client:
            response = client.patch("/api/v1/me", json={"displayName": "Updated"})
            assert response.status_code == 200
            updated = User.model_validate(response.json())
            assert updated.display_name == "Updated"
            assert updated.timezone == user.timezone
            assert updated.created_at == user.created_at
            assert updated.updated_at > user.updated_at
            assert client.get("/api/v1/me").json() == response.json()
            assert client.patch("/api/v1/me", json={"displayName": None}).json() == response.json()
            assert client.patch("/api/v1/me", json={"timezone": "Invalid/Zone"}).status_code == 422
        assert repository.get_by_id(user.id).display_name == "Updated"
    finally:
        with engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id == user.id))
        engine.dispose()
