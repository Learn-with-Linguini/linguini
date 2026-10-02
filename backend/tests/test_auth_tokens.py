"""Unit tests for Supabase JWT verification (no database or network)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import auth
from app.services.auth import (
    AuthConfigurationError,
    AuthSettings,
    InvalidTokenError,
    SupabaseTokenVerifier,
)

SUPABASE_URL = "https://project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
AUDIENCE = "authenticated"
KID = "test-signing-key"
HS_SECRET = "legacy-hs256-secret"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _settings(**overrides) -> AuthSettings:
    values = {
        "mode": "supabase",
        "supabase_url": SUPABASE_URL,
        "audience": AUDIENCE,
        "jwt_secret": None,
        "allow_anonymous": False,
    }
    values.update(overrides)
    return AuthSettings(**values)


class _FakeJWKClient:
    """Stands in for PyJWKClient; mirrors its unknown-kid failure."""

    def __init__(self, *args, **kwargs):
        pass

    def get_signing_key_from_jwt(self, token: str):
        header = jwt.get_unverified_header(token)
        if header.get("kid") != KID:
            raise jwt.exceptions.PyJWKClientError("Unable to find a signing key")
        return SimpleNamespace(key=_PRIVATE_KEY.public_key())


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.setattr(auth.jwt, "PyJWKClient", _FakeJWKClient)
    return SupabaseTokenVerifier(_settings())


def _token(key=_PRIVATE_KEY, kid: str = KID, **claims) -> str:
    payload = {
        "sub": str(uuid4()),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "email": "learner@example.com",
    }
    payload.update(claims)
    headers = {"kid": kid} if kid else {}
    return jwt.encode(payload, key, algorithm="RS256", headers=headers)


def test_valid_token_returns_identity(verifier):
    subject = str(uuid4())
    identity = verifier.verify(_token(sub=subject))
    assert identity.subject == subject
    assert identity.email == "learner@example.com"
    assert identity.is_anonymous is False


def test_expired_token_rejected(verifier):
    expired = datetime.now(UTC) - timedelta(minutes=5)
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(exp=expired))


def test_wrong_audience_rejected(verifier):
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(aud="service_role"))


def test_wrong_issuer_rejected(verifier):
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(iss="https://other.supabase.co/auth/v1"))


def test_unknown_kid_rejected(verifier):
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(kid="rotated-unknown-key"))


def test_anonymous_rejected_by_default(verifier):
    with pytest.raises(InvalidTokenError):
        verifier.verify(_token(is_anonymous=True))


def test_anonymous_accepted_when_allowed(monkeypatch):
    monkeypatch.setattr(auth.jwt, "PyJWKClient", _FakeJWKClient)
    verifier = SupabaseTokenVerifier(_settings(allow_anonymous=True))
    identity = verifier.verify(_token(is_anonymous=True))
    assert identity.is_anonymous is True


def test_unlisted_algorithm_rejected_without_jwks(verifier):
    def _no_lookup(token):
        raise AssertionError("JWKS lookup must not run for unlisted algorithms")

    verifier._jwks_client.get_signing_key_from_jwt = _no_lookup
    payload = {
        "sub": str(uuid4()),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, "secret", algorithm="HS384")
    with pytest.raises(InvalidTokenError):
        verifier.verify(token)


def test_empty_supabase_url_is_configuration_error():
    with pytest.raises(AuthConfigurationError):
        SupabaseTokenVerifier(_settings(supabase_url=""))


def test_unknown_auth_mode_is_configuration_error(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "nonsense")
    with pytest.raises(AuthConfigurationError):
        auth.load_auth_settings()


def test_hs256_verified_with_secret():
    verifier = SupabaseTokenVerifier(_settings(jwt_secret=HS_SECRET))
    payload = {
        "sub": str(uuid4()),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, HS_SECRET, algorithm="HS256")
    assert verifier.verify(token).subject == payload["sub"]


def test_hs256_without_secret_is_configuration_error():
    verifier = SupabaseTokenVerifier(_settings())
    payload = {
        "sub": str(uuid4()),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, HS_SECRET, algorithm="HS256")
    with pytest.raises(AuthConfigurationError):
        verifier.verify(token)
