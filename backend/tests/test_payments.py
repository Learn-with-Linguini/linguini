"""Tests for Stripe payment routes, webhook events, and tier allowances."""

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.repositories.users import UserRepository
from app.schemas.enums import AccountTier
from app.schemas.users import User
from app.services.stripe_service import DAILY_LESSON_LIMITS, StripeService


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

    result = service.handle_webhook_event(json.dumps(payload).encode("utf-8"), None)
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

    result = service.handle_webhook_event(json.dumps(payload).encode("utf-8"), None)
    assert result["status"] == "processed"
    updated_user = fake_user_repo.get_by_id(test_user.id)
    assert updated_user.tier == AccountTier.FREE


@pytest.mark.parametrize(
    ("event_type", "subscription_status", "initial_tier", "expected_tier"),
    [
        ("customer.subscription.updated", "active", AccountTier.FREE, AccountTier.PLUS),
        ("customer.subscription.updated", "past_due", AccountTier.PLUS, AccountTier.FREE),
        ("customer.subscription.deleted", "canceled", AccountTier.PLUS, AccountTier.FREE),
    ],
)
def test_checkout_subscription_events_keep_the_checkout_user(
    fake_user_repo, test_user, monkeypatch,
    event_type, subscription_status, initial_tier, expected_tier,
):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    other_user = fake_user_repo.get_or_create_by_auth_provider("other-learner", "other@example.com")
    fake_user_repo.set_tier(test_user.id, initial_tier.value)
    service = StripeService(fake_user_repo)
    service._secret_key = "sk_test_fake"
    service.client = MagicMock()
    service.client.checkout.sessions.create.return_value.url = "https://checkout.stripe.com/test"

    assert service.create_checkout_session(test_user.id, test_user.email) == "https://checkout.stripe.com/test"
    params = service.client.checkout.sessions.create.call_args.kwargs["params"]
    assert params["metadata"]["user_id"] == str(test_user.id)
    # Stripe copies subscription_data.metadata to the subscription, not session metadata.
    subscription_metadata = params.get("subscription_data", {}).get("metadata", {})
    payload = {
        "type": event_type,
        "data": {"object": {
            "id": "sub_test_checkout",
            "metadata": subscription_metadata,
            "status": subscription_status,
        }},
    }

    result = service.handle_webhook_event(json.dumps(payload).encode(), None)

    assert result == {"status": "processed", "type": event_type}
    assert fake_user_repo.get_by_id(test_user.id).tier == expected_tier
    assert fake_user_repo.get_by_id(other_user.id).tier == AccountTier.BETA
