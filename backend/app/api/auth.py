"""FastAPI wiring for bearer-token authentication."""

import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_demo_user_id
from app.repositories.postgres.users import PostgresUserRepository
from app.services.account_deletion import (
    AccountDeletionError,
    SupabaseAuthAdmin,
)
from app.services.auth import (
    AuthConfigurationError,
    AuthenticatedIdentity,
    AuthSettings,
    InvalidTokenError,
    SupabaseTokenVerifier,
    load_auth_settings,
)

_bearer = HTTPBearer(auto_error=False)


def get_auth_settings(request: Request) -> AuthSettings:
    """Auth settings loaded at app startup; falls back to loading on demand."""
    settings = getattr(request.app.state, "auth_settings", None)
    if settings is None:
        settings = load_auth_settings()
    return settings


def get_token_verifier(request: Request) -> SupabaseTokenVerifier:
    """Verifier built in the app lifespan; falls back to building on demand."""
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        verifier = SupabaseTokenVerifier(get_auth_settings(request))
    return verifier


def get_authenticated_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedIdentity | None:
    if credentials is None:
        return None
    try:
        return get_token_verifier(request).verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": str(exc)},
        ) from exc
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "auth_misconfigured",
                "message": "Authentication is not configured correctly.",
            },
        ) from exc


def get_current_user_id(
    request: Request,
    identity: Annotated[AuthenticatedIdentity | None, Depends(get_authenticated_identity)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> UUID:
    if identity is None:
        if settings.mode == "demo":
            return get_demo_user_id()
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthenticated",
                "message": "A valid bearer token is required.",
            },
        )
    repository = PostgresUserRepository(request.app.state.database_engine)
    user = repository.get_by_auth_provider_id(identity.subject)
    if user is not None:
        return user.id

    # Supabase JWTs remain cryptographically valid until their expiry time even
    # after the Auth identity is deleted. Confirm a missing local user still
    # exists upstream before auto-provisioning it, otherwise a stale token could
    # recreate an account that the learner just deleted.
    auth_admin = SupabaseAuthAdmin(
        settings.supabase_url,
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
    )
    try:
        if not auth_admin.user_exists(identity.subject):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "unauthenticated",
                    "message": "The sign-in account no longer exists.",
                },
            )
    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "auth_unavailable",
                "message": "Unable to confirm the sign-in account.",
            },
        ) from exc

    user = repository.get_or_create_by_auth_provider(identity.subject, identity.email)
    return user.id
