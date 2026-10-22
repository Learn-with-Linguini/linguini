"""Only authenticated Stripe events may change subscription tiers."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_payments import FakeUserRepository

from app.api.dependencies import get_stripe_service, get_user_service
from app.api.routes.payments import router
from app.schemas.enums import AccountTier
from app.services.stripe_service import StripeService

SECRET = "whsec_local_test"


def signature(payload, *, secret=SECRET, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + payload, hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture
def billing(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    repository = FakeUserRepository()
    user = repository.get_or_create_by_auth_provider("billing-test", "billing@example.com")
    service = StripeService(repository)
    # The previous implementation called a nonexistent SDK client.webhooks member.
    service.client = object()
    service._secret_key = "sk_test_fake"
    user_service = MagicMock()
    user_service.get_current_user.return_value = user
    user_service.set_user_tier.side_effect = lambda tier: repository.set_tier(user.id, tier)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stripe_service] = lambda: service
    app.dependency_overrides[get_user_service] = lambda: user_service
    payload = json.dumps({
        "id": "evt_local_test", "object": "event", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_local_test", "metadata": {"user_id": str(user.id)}}},
    }).encode()
    with TestClient(app) as client:
        yield client, service, repository, user, payload, user_service


@pytest.mark.parametrize("header", [None, "", "invalid", "t=1,v1=bad"])
def test_missing_or_invalid_signature_cannot_change_a_tier(billing, header):
    client, _service, repository, user, payload, _users = billing
    headers = {"Stripe-Signature": header} if header is not None else {}
    response = client.post("/api/v1/payments/webhook", content=payload, headers=headers)
    assert response.status_code == 400
    assert repository.get_by_id(user.id).tier == AccountTier.BETA


def test_valid_signature_uses_actual_sdk_and_does_not_need_an_api_key(billing):
    client, service, repository, user, payload, _users = billing
    service.client = None
    service._secret_key = None
    response = client.post(
        "/api/v1/payments/webhook", content=payload,
        headers={"Stripe-Signature": signature(payload)},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "processed", "type": "checkout.session.completed"}
    assert repository.get_by_id(user.id).tier == AccountTier.PLUS


@pytest.mark.parametrize("bad_payload", [b"not-json", b"[]", b'{}', b'\xff'])
def test_malformed_signed_payload_is_rejected_without_a_tier_write(billing, bad_payload):
    client, _service, repository, user, _payload, _users = billing
    response = client.post(
        "/api/v1/payments/webhook", content=bad_payload,
        headers={"Stripe-Signature": signature(bad_payload)},
    )
    assert response.status_code == 400
    assert repository.get_by_id(user.id).tier == AccountTier.BETA


@pytest.mark.parametrize("mismatch", ["body", "secret", "expired"])
def test_authenticity_and_recency_are_verified(billing, mismatch):
    client, _service, repository, user, payload, _users = billing
    header = signature(
        payload, secret="whsec_different" if mismatch == "secret" else SECRET,
        timestamp=int(time.time()) - 600 if mismatch == "expired" else None,
    )
    response = client.post(
        "/api/v1/payments/webhook", content=payload + b" " if mismatch == "body" else payload,
        headers={"Stripe-Signature": header},
    )
    assert response.status_code == 400
    assert repository.get_by_id(user.id).tier == AccountTier.BETA


def test_missing_secret_fails_closed_even_in_demo_mode(billing, monkeypatch):
    client, _service, repository, user, payload, _users = billing
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("AUTH_MODE", "demo")
    response = client.post("/api/v1/payments/webhook", content=payload)
    assert response.status_code == 503
    assert repository.get_by_id(user.id).tier == AccountTier.BETA


def test_normal_checkout_route_remains_available(billing):
    client, service, _repository, user, _payload, _users = billing
    service.create_checkout_session = MagicMock(return_value="https://checkout.stripe.com/test")
    response = client.post("/api/v1/payments/create-checkout-session", json={})
    assert response.status_code == 200
    assert response.json() == {"checkoutUrl": "https://checkout.stripe.com/test"}
    service.create_checkout_session.assert_called_once_with(
        user_id=user.id, email=user.email, return_url=None,
    )
