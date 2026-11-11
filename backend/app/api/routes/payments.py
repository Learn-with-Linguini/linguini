"""Payment and subscription endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from stripe import SignatureVerificationError

from app.api.dependencies import get_stripe_service, get_user_service
from app.services.stripe_service import (
    BillingCustomerNotLinked,
    InvalidPaymentReturnUrl,
    StripeConfigurationError,
    StripeService,
)
from app.services.users import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

StripeServiceDep = Annotated[StripeService, Depends(get_stripe_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]


class CreateCheckoutSessionRequest(BaseModel):
    returnUrl: str | None = Field(default=None, max_length=2048)


class CreatePortalSessionRequest(BaseModel):
    returnUrl: str | None = Field(default=None, max_length=2048)


class CheckoutSessionResponse(BaseModel):
    checkoutUrl: str


class PortalSessionResponse(BaseModel):
    portalUrl: str


class SubscriptionStatusResponse(BaseModel):
    tier: str
    dailyLessonLimit: int | None
    hasActiveSubscription: bool
    canUpgrade: bool


@router.get("/config")
def get_payment_config(service: StripeServiceDep) -> dict[str, str | None]:
    return service.get_public_config()


@router.get("/subscription-status", response_model=SubscriptionStatusResponse)
def get_subscription_status(
    user_service: UserServiceDep,
    stripe_service: StripeServiceDep,
) -> SubscriptionStatusResponse:
    user = user_service.get_current_user()
    data = stripe_service.get_subscription_status(user.id)
    return SubscriptionStatusResponse(**data)


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    user_service: UserServiceDep,
    stripe_service: StripeServiceDep,
) -> CheckoutSessionResponse:
    user = user_service.get_current_user()
    try:
        url = stripe_service.create_checkout_session(
            user_id=user.id,
            email=user.email,
            return_url=request.returnUrl,
        )
        return CheckoutSessionResponse(checkoutUrl=url)
    except InvalidPaymentReturnUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StripeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to create Stripe checkout session.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate checkout. Please try again.",
        ) from exc


@router.post("/create-portal-session", response_model=PortalSessionResponse)
def create_portal_session(
    request: CreatePortalSessionRequest,
    user_service: UserServiceDep,
    stripe_service: StripeServiceDep,
) -> PortalSessionResponse:
    user = user_service.get_current_user()
    try:
        url = stripe_service.create_portal_session(
            user_id=user.id,
            email=user.email,
            return_url=request.returnUrl,
        )
        return PortalSessionResponse(portalUrl=url)
    except BillingCustomerNotLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidPaymentReturnUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StripeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to create Stripe customer portal session.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to open customer portal. Please try again.",
        ) from exc


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_service: StripeServiceDep,
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
) -> dict[str, Any]:
    payload = await request.body()
    try:
        return stripe_service.handle_webhook_event(payload, stripe_signature)
    except StripeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment webhook verification is not configured.",
        ) from exc
    except (ValueError, SignatureVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook verification failed.",
        ) from exc
