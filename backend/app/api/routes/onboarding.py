"""Authenticated onboarding placement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.auth import get_current_user_id
from app.repositories.postgres.onboarding import OnboardingPlacementRepository
from app.schemas.onboarding import (
    PlacementAnswerCheck,
    PlacementAnswerFeedback,
    PlacementResult,
    PlacementSubmission,
    PlacementTest,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def repository(
    request: Request,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> OnboardingPlacementRepository:
    return OnboardingPlacementRepository(request.app.state.database_engine, user_id)


@router.get("/placement", response_model=PlacementTest)
def get_placement(
    language_code: Annotated[str, Query(alias="languageCode")],
    placement: Annotated[OnboardingPlacementRepository, Depends(repository)],
) -> PlacementTest:
    try:
        result = placement.test(language_code)
    except ValueError as exc:
        raise HTTPException(
            404, detail={"code": "placement_unavailable", "message": str(exc)}
        ) from exc
    if not result.questions:
        raise HTTPException(
            404,
            detail={
                "code": "placement_unavailable",
                "message": "Placement questions are unavailable.",
            },
        )
    return result


@router.post("/placement", response_model=PlacementResult)
def submit_placement(
    submission: PlacementSubmission,
    placement: Annotated[OnboardingPlacementRepository, Depends(repository)],
) -> PlacementResult:
    try:
        level = placement.submit(submission)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "placement_incomplete", "message": str(exc)}
        ) from exc
    return PlacementResult(
        proficiency_level=level,
        message="Great work — your first learning path is ready!",
    )


@router.post("/placement/check", response_model=PlacementAnswerFeedback)
def check_placement_answer(
    answer: PlacementAnswerCheck,
    placement: Annotated[OnboardingPlacementRepository, Depends(repository)],
) -> PlacementAnswerFeedback:
    try:
        correct, correct_option = placement.check_answer(answer.question_id, answer.answer)
    except ValueError as exc:
        raise HTTPException(
            404, detail={"code": "placement_question_not_found", "message": str(exc)}
        ) from exc
    return PlacementAnswerFeedback(correct=correct, correct_option=correct_option)
