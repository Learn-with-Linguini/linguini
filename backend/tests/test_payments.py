"""Tests for Stripe payment routes, webhook events, and tier allowances."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_stripe_service, get_user_service
from app.api.routes.payments import router
from app.repositories.users import UserRepository
from app.schemas.enums import AccountTier
from app.schemas.users import User
from app.services.stripe_service import (
    DAILY_LESSON_LIMITS,
    InvalidPaymentReturnUrl,
    StripeService,
)
from app.services.users import UserService

WEBHOOK_SECRET = "whsec_security_test"


def signed_payload(event, *, secret=WEBHOOK_SECRET, timestamp=None):
    payload = json.dumps(event).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    signed = str(timestamp).encode() + b"." + payload
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return payload, f"t={timestamp},v1={signature}"


@pytest.fixture(autouse=True)
def billing_environment(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("FRONTEND_URL", "https://learnwithlinguini.com")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)


def billing_client(service, repository, user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stripe_service] = lambda: service
    app.dependency_overrides[get_user_service] = lambda: UserService(repository, user.id)
    return TestClient(app)


class FakeUserRepository(UserRepository):
    def __init__(self):
        self.users: dict[str, User] = {}

    def get_by_id(self, user_id):
        return self.users.get(str(user_id))

    def get_or_create_by_auth_provider(self, auth_provider_id, email):
        user = User(
            id=uuid4(),
            auth_provider_id=auth_provider_id,
            display_name="Test Learner",
            email=email,
            tier=AccountTier.BETA,
        )
        self.users[str(user.id)] = user
        return user

    def update(self, user_id, request):
        user = self.get_by_id(user_id)
        if not user:
            return None
        updated = user.model_copy(update=request.model_dump(exclude_unset=True))
        self.users[str(user_id)] = updated
        return updated

    def set_tier(self, user_id, tier):
        user = self.get_by_id(user_id)
        if not user:
            return None
        updated = user.model_copy(update={"tier": AccountTier(tier)})
        self.users[str(user_id)] = updated
        return updated


@pytest.fixture
def fake_user_repo():
    repo = FakeUserRepository()
    return repo


@pytest.fixture
def test_user(fake_user_repo):
    user = User(
        id=uuid4(),
        auth_provider_id="test-auth-id",
        display_name="Dev Tester",
        email="developer@learnwithlinguini.com",
        tier=AccountTier.BETA,
    )
    fake_user_repo.users[str(user.id)] = user
    return user


def test_tier_limits_mapping():
    assert DAILY_LESSON_LIMITS[AccountTier.BETA] is None
    assert DAILY_LESSON_LIMITS[AccountTier.FREE] == 1
    assert DAILY_LESSON_LIMITS[AccountTier.PLUS] == 10


def test_stripe_service_subscription_status(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    status = service.get_subscription_status(test_user.id)
    assert status["tier"] == "beta"
    assert status["dailyLessonLimit"] is None
    assert status["canUpgrade"] is True
    assert status["hasActiveSubscription"] is False

    # Upgrade to Plus
    fake_user_repo.set_tier(test_user.id, AccountTier.PLUS.value)
    status_plus = service.get_subscription_status(test_user.id)
    assert status_plus["tier"] == "plus"
    assert status_plus["dailyLessonLimit"] == 10
    assert status_plus["canUpgrade"] is False
    assert status_plus["hasActiveSubscription"] is True


def test_stripe_service_webhook_checkout_completed(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    service._secret_key = "sk_test_fake"
    service.client = MagicMock()

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": str(test_user.id),
                "metadata": {"user_id": str(test_user.id)},
                "customer": "cus_test_abc",
                "subscription": "sub_test_xyz",
            }
        },
    }

    result = service.handle_webhook_event(*signed_payload(payload))
    assert result["status"] == "processed"
    updated_user = fake_user_repo.get_by_id(test_user.id)
    assert updated_user.tier == AccountTier.PLUS


def test_stripe_service_webhook_subscription_deleted(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    service._secret_key = "sk_test_fake"
    fake_user_repo.set_tier(test_user.id, AccountTier.PLUS.value)
    service.client = MagicMock()

    payload = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_test_xyz",
                "metadata": {"user_id": str(test_user.id)},
                "status": "canceled",
            }
        },
    }

    result = service.handle_webhook_event(*signed_payload(payload))
    assert result["status"] == "processed"
    updated_user = fake_user_repo.get_by_id(test_user.id)
    assert updated_user.tier == AccountTier.FREE


@pytest.mark.parametrize("configured_secret", [None, WEBHOOK_SECRET])
def test_unsigned_webhook_cannot_change_tier(
    fake_user_repo, test_user, monkeypatch, configured_secret
):
    if configured_secret is None:
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    service = StripeService(fake_user_repo)
    client = billing_client(service, fake_user_repo, test_user)
    response = client.post("/api/v1/payments/webhook", json={
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"user_id": str(test_user.id)}}},
    })
    assert response.status_code == (503 if configured_secret is None else 400)
    assert fake_user_repo.get_by_id(test_user.id).tier == AccountTier.BETA


@pytest.mark.parametrize("attack", ["wrong_secret", "tampered", "expired", "malformed"])
def test_invalid_webhook_signatures_cannot_change_tier(fake_user_repo, test_user, attack):
    service = StripeService(fake_user_repo)
    client = billing_client(service, fake_user_repo, test_user)
    payload, signature = signed_payload({
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"user_id": str(test_user.id)}}},
    }, secret="wrong-secret" if attack == "wrong_secret" else WEBHOOK_SECRET,
        timestamp=int(time.time()) - 301 if attack == "expired" else None)
    if attack == "tampered":
        payload += b" "
    if attack == "malformed":
        signature = "invalid"
    response = client.post("/api/v1/payments/webhook", content=payload,
                           headers={"Stripe-Signature": signature})
    assert response.status_code == 400
    assert fake_user_repo.get_by_id(test_user.id).tier == AccountTier.BETA


def test_signed_webhook_works_without_api_key(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    assert service.client is None
    client = billing_client(service, fake_user_repo, test_user)
    payload, signature = signed_payload({
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"user_id": str(test_user.id)}}},
    })
    response = client.post("/api/v1/payments/webhook", content=payload,
                           headers={"Stripe-Signature": signature})
    assert response.status_code == 200
    assert fake_user_repo.get_by_id(test_user.id).tier == AccountTier.PLUS


def test_tier_switch_endpoint_is_removed(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    client = billing_client(service, fake_user_repo, test_user)
    response = client.post("/api/v1/payments/test-set-tier", json={"tier": "plus"})
    assert response.status_code == 404
    assert fake_user_repo.get_by_id(test_user.id).tier == AccountTier.BETA


@pytest.mark.parametrize("return_url", [
    "https://evil.example/payment",
    "https://learnwithlinguini.com.evil.example/payment",
    "https://learnwithlinguini.com@evil.example/payment",
    "https://attacker@learnwithlinguini.com/payment",
    "https://learnwithlinguini.com:444/payment",
    "http://learnwithlinguini.com/payment",
    "//learnwithlinguini.com/payment",
    "javascript:alert(1)",
    "/payment",
    "https://learnwithlinguini.com/payment#evil",
    "https://learnwithlinguini.com\\@evil.example/payment",
    "https://learnwithlinguini.com/\npayment",
    "https://learnwithlinguini.com:invalid/payment",
    "",
])
@pytest.mark.parametrize("method", ["create_checkout_session", "create_portal_session"])
def test_untrusted_return_urls_rejected_before_stripe(
    fake_user_repo, test_user, return_url, method
):
    service = StripeService(fake_user_repo)
    service._secret_key = "sk_test_fake"
    service.client = MagicMock()
    with pytest.raises(InvalidPaymentReturnUrl):
        getattr(service, method)(test_user.id, test_user.email, return_url)
    assert service.client.mock_calls == []


def test_return_url_rejection_is_client_error(fake_user_repo, test_user):
    service = StripeService(fake_user_repo)
    client = billing_client(service, fake_user_repo, test_user)
    for path in ("create-checkout-session", "create-portal-session"):
        response = client.post(f"/api/v1/payments/{path}", json={
            "returnUrl": "https://evil.example/payment",
        })
        assert response.status_code == 400


def stripe_service_with_customer(repository, user):
    service = StripeService(repository)
    service._secret_key = "sk_test_fake"
    service.client = MagicMock()
    service.client.customers.search.return_value = SimpleNamespace(data=[
        SimpleNamespace(id="cus_owned", metadata={"user_id": str(user.id)}),
    ])
    service.client.checkout.sessions.create.return_value.url = "https://checkout.stripe.com/test"
    service.client.billing_portal.sessions.create.return_value.url = "https://billing.stripe.com/test"
    return service


def test_checkout_and_portal_share_owned_customer(fake_user_repo, test_user):
    service = stripe_service_with_customer(fake_user_repo, test_user)
    service.create_checkout_session(test_user.id, test_user.email,
                                    "https://learnwithlinguini.com/payment?source=app")
    service.create_portal_session(test_user.id, test_user.email)
    params = service.client.checkout.sessions.create.call_args.kwargs["params"]
    assert params["customer"] == "cus_owned"
    assert params["metadata"] == {"user_id": str(test_user.id)}
    assert params["subscription_data"]["metadata"] == {"user_id": str(test_user.id)}
    assert params["success_url"] == (
        "https://learnwithlinguini.com/payment?source=app&status=success"
        "&session_id={CHECKOUT_SESSION_ID}"
    )
    assert params["cancel_url"] == (
        "https://learnwithlinguini.com/payment?source=app&status=cancelled"
    )
    portal = service.client.billing_portal.sessions.create.call_args.kwargs["params"]
    assert portal == {"customer": "cus_owned", "return_url": "https://learnwithlinguini.com/payment"}
    service.client.customers.list.assert_not_called()
    service.client.customers.create.assert_not_called()


def test_shared_email_does_not_grant_portal_access(fake_user_repo, test_user):
    service = stripe_service_with_customer(fake_user_repo, test_user)
    service.client.customers.list.return_value = SimpleNamespace(data=[
        SimpleNamespace(id="cus_other_user", email=test_user.email),
    ])
    service.client.customers.search.return_value = SimpleNamespace(data=[])
    client = billing_client(service, fake_user_repo, test_user)
    response = client.post("/api/v1/payments/create-portal-session", json={})
    assert response.status_code == 409
    service.client.customers.list.assert_not_called()
    service.client.customers.create.assert_not_called()
    service.client.billing_portal.sessions.create.assert_not_called()


def test_checkout_creates_owned_customer_idempotently(fake_user_repo, test_user):
    service = stripe_service_with_customer(fake_user_repo, test_user)
    service.client.customers.search.return_value = SimpleNamespace(data=[])
    service.client.customers.create.return_value = SimpleNamespace(id="cus_new_owned")
    service.create_checkout_session(test_user.id, test_user.email)
    service.client.customers.create.assert_called_once_with(
        params={"email": test_user.email, "metadata": {"user_id": str(test_user.id)}},
        options={"idempotency_key": f"linguini-customer-{test_user.id}"},
    )
    assert service.client.checkout.sessions.create.call_args.kwargs["params"][
        "customer"
    ] == "cus_new_owned"


def test_mismatched_customer_metadata_fails_closed(fake_user_repo, test_user):
    service = stripe_service_with_customer(fake_user_repo, test_user)
    service.client.customers.search.return_value.data[0].metadata["user_id"] = str(uuid4())
    with pytest.raises(RuntimeError, match="does not belong"):
        service.create_portal_session(test_user.id, test_user.email)
    service.client.billing_portal.sessions.create.assert_not_called()


def test_local_development_origin_allowed(fake_user_repo, test_user, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    service = stripe_service_with_customer(fake_user_repo, test_user)
    service.create_portal_session(test_user.id, test_user.email, "http://localhost:5173/payment")
    assert service.client.billing_portal.sessions.create.call_args.kwargs["params"][
        "return_url"
    ] == "http://localhost:5173/payment"
