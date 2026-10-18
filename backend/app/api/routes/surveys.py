"""Learner satisfaction and product improvement survey endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import get_authenticated_identity, get_current_user_id
from app.api.dependencies import get_survey_repository, get_user_repository
from app.repositories.postgres.surveys import PostgresSurveyRepository
from app.repositories.users import UserRepository
from app.schemas.surveys import CreateSurveyRequest, SurveyResponse
from app.services.auth import AuthenticatedIdentity

router = APIRouter(prefix="/surveys", tags=["surveys"])


@router.post(
    "",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_survey(
    request: CreateSurveyRequest,
    repository: Annotated[PostgresSurveyRepository, Depends(get_survey_repository)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    identity: Annotated[AuthenticatedIdentity | None, Depends(get_authenticated_identity)],
) -> SurveyResponse:
    email = identity.email if identity is not None else None
    if email is None:
        try:
            user = user_repo.get_by_id(user_id)
            if user:
                email = user.email
        except Exception:
            pass

    try:
        return repository.create(
            user_id=user_id,
            email=email,
            request=request,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "survey_save_failed", "message": "Unable to save survey response."},
        ) from exc
