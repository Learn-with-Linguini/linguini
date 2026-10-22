"""Stripe billing and subscription service."""

from __future__ import annotations

import logging
import secrets
from typing import Any
from uuid import UUID

from stripe import StripeClient, Webhook

from app.config import (
    get_frontend_url,
    get_stripe_plus_price_id,
    get_stripe_publishable_key,
    get_stripe_secret_key,
    get_stripe_webhook_secret,
)
from app.repositories.users import UserRepository
from app.schemas.enums import AccountTier

logger = logging.getLogger(__name__)

DAILY_LESSON_LIMITS: dict[AccountTier, int | None] = {
    AccountTier.BETA: None,  # Unlimited lessons per day during beta
    AccountTier.FREE: 1,     # 1 lesson per day for free tier
    AccountTier.PLUS: 10,    # 10 lessons per day for plus tier
}


class StripeConfigurationError(Exception):
    """Raised when Stripe credentials or settings are missing."""


class StripeService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository
        secret_key = get_stripe_secret_key()
        self._secret_key = secret_key
        self.client = StripeClient(secret_key) if secret_key else None

    def _require_client(self) -> StripeClient:
        if self.client is None or not self._secret_key:
            raise StripeConfigurationError(
                "Stripe secret key is not configured. Set STRIPE_SECRET_KEY in your environment."
            )
        return self.client

    def get_public_config(self) -> dict[str, Any]:
        return {
            "publishableKey": get_stripe_publishable_key(),
            "plusPriceId": get_stripe_plus_price_id(),
        }

    def get_subscription_status(self, user_id: UUID) -> dict[str, Any]:
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found.")
        tier = user.tier
        limit = DAILY_LESSON_LIMITS.get(tier, None)
        return {
            "tier": tier.value if hasattr(tier, "value") else str(tier),
            "dailyLessonLimit": limit,
            "hasActiveSubscription": tier == AccountTier.PLUS,
            "canUpgrade": tier != AccountTier.PLUS,
        }

    def create_checkout_session(
        self,
        user_id: UUID,
        email: str | None,
        return_url: str | None = None,
    ) -> str:
        client = self._require_client()
        base_url = return_url or f"{get_frontend_url()}/payment"
        price_id = get_stripe_plus_price_id()
        ident_suffix = secrets.token_hex(4)

        session_params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "client_reference_id": str(user_id),
            "metadata": {
                "user_id": str(user_id),
            },
            "success_url": f"{base_url}?status=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base_url}?status=cancelled",
            "integration_identifier": f"linguini_sub_{ident_suffix}",
        }
        if email:
            session_params["customer_email"] = email

        session = client.checkout.sessions.create(params=session_params)
        if not session.url:
            raise RuntimeError("Stripe Checkout did not return a checkout URL.")
        return session.url

    def create_portal_session(
        self,
        user_id: UUID,
        email: str | None = None,
        return_url: str | None = None,
    ) -> str:
        client = self._require_client()
        base_url = return_url or f"{get_frontend_url()}/payment"

        # Search for customer by metadata or email
        customer_id: str | None = None
        if email:
            customers = client.customers.list(params={"email": email, "limit": 1})
            if customers.data:
                customer_id = customers.data[0].id

        if not customer_id:
            customers_search = client.customers.search(
                params={"query": f"metadata['user_id']:'{user_id}'", "limit": 1}
            )
            if customers_search.data:
                customer_id = customers_search.data[0].id

        if not customer_id:
            # Create a customer so portal can be opened
            customer = client.customers.create(
                params={
                    "email": email,
                    "metadata": {"user_id": str(user_id)},
                }
            )
            customer_id = customer.id

        portal_session = client.billing_portal.sessions.create(
            params={
                "customer": customer_id,
                "return_url": base_url,
            }
        )
        return portal_session.url

    def handle_webhook_event(self, payload: bytes, sig_header: str | None) -> dict[str, Any]:
        webhook_secret = get_stripe_webhook_secret()
        if not webhook_secret:
            raise StripeConfigurationError("STRIPE_WEBHOOK_SECRET is required for Stripe webhooks.")

        if not sig_header:
            raise ValueError("Stripe-Signature is required for Stripe webhooks.")

        event = Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=webhook_secret,
        ).to_dict()
        event_type = event.get("type")
        data = event.get("data")
        if (
            not isinstance(event_type, str) or not event_type
            or not isinstance(data, dict) or not isinstance(data.get("object"), dict)
        ):
            raise ValueError("Invalid Stripe event structure.")
        obj = data["object"]

        logger.info("Handling Stripe webhook event: %s", event_type)

        if event_type == "checkout.session.completed":
            self._on_checkout_completed(obj)
        elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
            self._on_subscription_updated(obj)
        elif event_type == "customer.subscription.deleted":
            self._on_subscription_deleted(obj)

        return {"status": "processed", "type": event_type}

    def _extract_metadata(self, obj: Any) -> dict:
        if isinstance(obj, dict):
            return obj.get("metadata") or {}
        return getattr(obj, "metadata", None) or {}

    def _on_checkout_completed(self, session: Any) -> None:
        metadata = self._extract_metadata(session)
        user_id_str = (
            metadata.get("user_id")
            or getattr(session, "client_reference_id", None)
            or (session.get("client_reference_id") if isinstance(session, dict) else None)
        )
        if not user_id_str:
            logger.warning(
                "Checkout session completed without user_id in metadata or client_reference_id."
            )
            return

        try:
            user_id = UUID(str(user_id_str))
            logger.info("Upgrading user %s to Plus tier after successful checkout.", user_id)
            self.user_repository.set_tier(user_id, AccountTier.PLUS.value)
        except Exception:
            logger.exception("Failed to upgrade user %s after checkout.", user_id_str)

    def _on_subscription_updated(self, subscription: Any) -> None:
        metadata = self._extract_metadata(subscription)
        user_id_str = metadata.get("user_id")
        if isinstance(subscription, dict):
            status = subscription.get("status")
        else:
            status = getattr(subscription, "status", None)

        if not user_id_str:
            return

        try:
            user_id = UUID(str(user_id_str))
            if status in ("active", "trialing"):
                self.user_repository.set_tier(user_id, AccountTier.PLUS.value)
            elif status in ("canceled", "unpaid", "past_due"):
                self.user_repository.set_tier(user_id, AccountTier.FREE.value)
        except Exception:
            logger.exception("Failed to update user %s subscription status.", user_id_str)

    def _on_subscription_deleted(self, subscription: Any) -> None:
        metadata = self._extract_metadata(subscription)
        user_id_str = metadata.get("user_id")
        if not user_id_str:
            return

        try:
            user_id = UUID(str(user_id_str))
            logger.info(
                "Downgrading user %s to Free tier after subscription cancellation.",
                user_id,
            )
            self.user_repository.set_tier(user_id, AccountTier.FREE.value)
        except Exception:
            logger.exception(
                "Failed to downgrade user %s after subscription cancellation.",
                user_id_str,
            )
