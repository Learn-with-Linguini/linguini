from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import get_authenticated_identity
from app.api.dependencies import (
    get_account_deletion_service,
    get_language_profile_service,
    get_user_service,
)
from app.repositories.users import UserRepositoryError
from app.schemas.users import (
    CreateLanguageProfileRequest,
    LanguageProfile,
    UpdateLanguageProfileRequest,
    UpdateUserRequest,
    User,
)
from app.services.account_deletion import (
    AccountDeletionError,
    AccountDeletionNotConfiguredError,
    AccountDeletionService,
)
from app.services.auth import AuthenticatedIdentity
from app.services.language_profiles import LanguageProfileService
from app.services.users import UserNotFoundError, UserService

router = APIRouter(tags=["users"])


@router.get("/me", response_model=User)
def get_me(service: Annotated[UserService, Depends(get_user_service)]) -> User:
    try:
        return service.get_current_user()
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "user_not_found", "message": str(exc)},
        ) from exc
    except UserRepositoryError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "user_storage_error", "message": "Unable to load demo user data."},
        ) from exc


@router.patch("/me", response_model=User)
def update_me(
    request: UpdateUserRequest, service: Annotated[UserService, Depends(get_user_service)]
) -> User:
    return service.update_current_user(request)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    service: Annotated[UserService, Depends(get_user_service)],
    deletion: Annotated[AccountDeletionService, Depends(get_account_deletion_service)],
    identity: Annotated[AuthenticatedIdentity | None, Depends(get_authenticated_identity)],
) -> Response:
    if identity is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "account_deletion_unavailable",
                "message": "Account deletion requires a signed-in Supabase account.",
            },
        )
    user = service.get_current_user()
    if user.auth_provider_id != identity.subject:
        raise HTTPException(
            status_code=403,
            detail={"code": "account_mismatch", "message": "Account verification failed."},
        )
    try:
        deletion.delete_account(user.id, identity.subject)
    except AccountDeletionNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "account_deletion_unavailable", "message": str(exc)},
        ) from exc
    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "account_deletion_failed",
                "message": "We couldn't delete your account. Please try again.",
            },
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/language-profiles", response_model=list[LanguageProfile])
def list_language_profiles(
    service: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> list[LanguageProfile]:
    return service.list_profiles()


@router.post(
    "/me/language-profiles",
    response_model=LanguageProfile,
    status_code=status.HTTP_201_CREATED,
)
def create_language_profile(
    request: CreateLanguageProfileRequest,
    service: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> LanguageProfile:
    return service.create(request)


@router.patch("/me/language-profiles/{profile_id}", response_model=LanguageProfile)
def update_language_profile(
    profile_id: UUID,
    request: UpdateLanguageProfileRequest,
    service: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> LanguageProfile:
    return service.update(profile_id, request)
