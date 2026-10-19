"""Learner satisfaction and product improvement survey endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import get_auth_settings, get_authenticated_identity
from app.api.dependencies import get_survey_repository, get_user_repository
from app.config import get_demo_user_id
from app.repositories.postgres.surveys import PostgresSurveyRepository
from app.repositories.users import UserRepository
from app.schemas.surveys import CreateSurveyRequest, SurveyResponse
from app.services.auth import AuthenticatedIdentity, AuthSettings

router = APIRouter(prefix="/surveys", tags=["surveys"])


@router.post(
    "",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_survey(
    request: CreateSurveyRequest,
    repository: Annotated[PostgresSurveyRepository, Depends(get_survey_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    identity: Annotated[AuthenticatedIdentity | None, Depends(get_authenticated_identity)] = None,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)] = None,
) -> SurveyResponse:
    user_id: UUID | None = None
    account_email: str | None = None

    if identity is not None:
        user = user_repo.get_by_auth_provider_id(identity.subject)
        if user is not None:
            user_id = user.id
            account_email = user.email or identity.email
        else:
            account_email = identity.email
    elif settings is not None and settings.mode == "demo":
        try:
            demo_id = get_demo_user_id()
            user = user_repo.get_by_id(demo_id)
            if user is not None:
                user_id = user.id
                account_email = user.email
        except Exception:
            pass

    # If follow-up is requested, save provided email or account email; otherwise save NULL.
    if request.receive_follow_up:
        provided = request.email.strip() if request.email else None
        email_to_save = provided or account_email
    else:
        email_to_save = None

    try:
        return repository.create(
            user_id=user_id,
            email=email_to_save,
            request=request,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "survey_save_failed", "message": "Unable to save survey response."},
        ) from exc
