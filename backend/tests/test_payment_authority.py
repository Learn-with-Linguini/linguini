"""Learners can enter billing flows but cannot grant themselves a paid tier."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_stripe_service, get_user_service
from app.api.routes.payments import router as payments_router
from app.api.routes.users import router as users_router
from app.schemas.enums import AccountTier
from app.schemas.users import User


@pytest.fixture
def billing():
    user = User(auth_provider_id="billing-learner", display_name="Learner", tier="free")
    users = MagicMock()
    users.get_current_user.return_value = user
    users.set_user_tier.return_value = user.model_copy(update={"tier": AccountTier.PLUS})
    stripe = MagicMock()
    stripe.create_checkout_session.return_value = "https://checkout.stripe.com/test"
    stripe.create_portal_session.return_value = "https://billing.stripe.com/test"
    stripe.get_subscription_status.return_value = {
        "tier": "free", "dailyLessonLimit": 1, "hasActiveSubscription": False, "canUpgrade": True,
    }
    app = FastAPI()
    app.include_router(payments_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_stripe_service] = lambda: stripe
    with TestClient(app) as client:
        yield client, user, users, stripe


def test_authenticated_learner_cannot_use_tier_testing_endpoint(billing):
    client, _user, users, _stripe = billing
    response = client.post("/api/v1/payments/test-set-tier", json={"tier": "plus"})
    assert response.status_code == 404
    users.set_user_tier.assert_not_called()


def test_payment_contract_does_not_publish_tier_testing_endpoint(billing):
    client, _user, _users, _stripe = billing
    schema = client.get("/openapi.json").json()
    assert "/api/v1/payments/test-set-tier" not in schema["paths"]


def test_normal_billing_flows_identify_the_authenticated_account(billing):
    client, user, users, stripe = billing
    assert client.get("/api/v1/payments/subscription-status").json()["tier"] == "free"
    stripe.get_subscription_status.assert_called_once_with(user.id)
    for path, method, field in (
        ("create-checkout-session", stripe.create_checkout_session, "checkoutUrl"),
        ("create-portal-session", stripe.create_portal_session, "portalUrl"),
    ):
        response = client.post(f"/api/v1/payments/{path}", json={"returnUrl": "https://app.test/payment"})
        assert response.status_code == 200
        assert response.json()[field] == method.return_value
        method.assert_called_once_with(user_id=user.id, email=user.email,
                                       return_url="https://app.test/payment")
    users.set_user_tier.assert_not_called()


def test_account_profile_update_cannot_set_tier(billing):
    client, _user, users, _stripe = billing
    response = client.patch("/api/v1/me", json={"tier": "plus"})
    assert response.status_code == 422
    users.update_current_user.assert_not_called()
