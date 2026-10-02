from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_practice_service
from app.schemas.sessions import (
    CreateSessionRequest,
    GenerateSessionPlanRequest,
    ReviewPracticeRequest,
    Session,
    SessionDetailResponse,
    SessionSummaryResponse,
)
from app.schemas.tasks import SessionTaskPublic
from app.services.practice import PracticeService

router = APIRouter(prefix="/sessions", tags=["sessions"])

PracticeServiceDep = Annotated[PracticeService, Depends(get_practice_service)]


@router.post(
    "",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_session(
    request: CreateSessionRequest, service: PracticeServiceDep
) -> SessionDetailResponse:
    return service.create(request)


@router.get("/active", response_model=SessionDetailResponse | None)
def get_active_session(service: PracticeServiceDep) -> SessionDetailResponse | None:
    return service.active()


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: UUID, service: PracticeServiceDep) -> SessionDetailResponse:
    return service.get(session_id)


@router.post("/{session_id}/analyze", response_model=SessionDetailResponse)
def analyze_session(session_id: UUID, service: PracticeServiceDep) -> SessionDetailResponse:
    return service.analyze(session_id)


@router.post(
    "/{session_id}/generate-plan",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_session_plan(
    session_id: UUID, request: GenerateSessionPlanRequest, service: PracticeServiceDep
) -> SessionDetailResponse:
    return service.analyze(session_id)


@router.get("/{session_id}/tasks", response_model=list[SessionTaskPublic])
def list_session_tasks(session_id: UUID, service: PracticeServiceDep) -> list[SessionTaskPublic]:
    return service.get(session_id).tasks


@router.put("/{session_id}/review", response_model=SessionDetailResponse)
def review_session(
    session_id: UUID, request: ReviewPracticeRequest, service: PracticeServiceDep
) -> SessionDetailResponse:
    return service.review(session_id, request)


@router.get("/{session_id}/summary", response_model=SessionSummaryResponse)
def get_session_summary(session_id: UUID, service: PracticeServiceDep) -> SessionSummaryResponse:
    return service.summary(session_id)


@router.post("/{session_id}/complete", response_model=Session)
def complete_session(session_id: UUID, service: PracticeServiceDep) -> Session:
    return service.complete(session_id)


@router.post("/{session_id}/abandon", response_model=Session)
def abandon_session(session_id: UUID, service: PracticeServiceDep) -> Session:
    return service.abandon(session_id)


@router.get("/{session_id}/review-word")
def check_review_word(
    session_id: UUID, service: PracticeServiceDep, label: str = Query(min_length=1, max_length=200)
):
    return service.check_word(session_id, label)
