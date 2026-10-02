"""API-level auth wiring: 401 paths exercise the real dependencies."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.repositories.postgres.users import users
from app.services import auth

SUPABASE_URL = "https://project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
KID = "test-signing-key"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJWKClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_signing_key_from_jwt(self, token: str):
        header = jwt.get_unverified_header(token)
        if header.get("kid") != KID:
            raise jwt.exceptions.PyJWKClientError("Unable to find a signing key")
        return SimpleNamespace(key=_PRIVATE_KEY.public_key())


def _bearer(sub: str, email: str | None = "learner@example.com") -> dict[str, str]:
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    if email is not None:
        payload["email"] = email
    token = jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})
    return {"Authorization": f"Bearer {token}"}


def _app_without_lifespan():
    """401 paths never touch the engine; a placeholder avoids running lifespan."""
    app = create_app()
    app.state.database_engine = None
    return app


def test_missing_authorization_header_returns_401(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    response = TestClient(_app_without_lifespan()).get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


def test_garbage_bearer_token_returns_401(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    client = TestClient(_app_without_lifespan())
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


@pytest.fixture
def supabase_client(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setattr(auth.jwt, "PyJWKClient", _FakeJWKClient)
    with TestClient(create_app()) as client:
        yield client


def test_first_request_provisions_one_user(supabase_client):
    sub = str(uuid4())
    first = supabase_client.get("/api/v1/me", headers=_bearer(sub, "new.learner@example.com"))
    assert first.status_code == 200
    second = supabase_client.get("/api/v1/me", headers=_bearer(sub, "new.learner@example.com"))
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["displayName"] == "new.learner"
    engine = supabase_client.app.state.database_engine
    with engine.connect() as connection:
        count = connection.execute(
            select(func.count()).select_from(users).where(users.c.auth_provider_id == sub)
        ).scalar_one()
    assert count == 1


def test_distinct_subjects_get_isolated_resources(supabase_client):
    sub_a, sub_b = str(uuid4()), str(uuid4())
    user_a = supabase_client.get("/api/v1/me", headers=_bearer(sub_a)).json()
    user_b = supabase_client.get("/api/v1/me", headers=_bearer(sub_b)).json()
    assert user_a["id"] != user_b["id"]

    profile = supabase_client.post(
        "/api/v1/me/language-profiles",
        headers=_bearer(sub_a),
        json={
            "sourceLanguageCode": "en",
            "targetLanguageCode": "zh",
            "proficiencyLevel": "B1",
        },
    )
    assert profile.status_code == 201
    journal = supabase_client.put(
        "/api/v1/journal/today",
        headers=_bearer(sub_a),
        json={"languageProfileId": profile.json()["id"], "content": "Private entry"},
    )
    assert journal.status_code == 200

    assert supabase_client.get("/api/v1/journals", headers=_bearer(sub_b)).json() == []
    inaccessible = supabase_client.get(
        f"/api/v1/journals/{journal.json()['id']}", headers=_bearer(sub_b)
    )
    assert inaccessible.status_code == 404
