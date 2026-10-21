from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_journal_service
from app.api.errors import service_not_implemented
from app.schemas.journals import (
    AddJournalMediaRequest,
    CompleteJournalRequest,
    CreateJournalRevisionRequest,
    GenerateJournalSuggestionsRequest,
    Journal,
    JournalDetailResponse,
    JournalMedia,
    JournalRevision,
    JournalSuggestion,
    JournalTodayContextResponse,
    UpdateJournalRequest,
    UpsertTodayJournalRequest,
)
from app.services.journals import JournalService

router = APIRouter(tags=["journals"])

JournalServiceDep = Annotated[JournalService, Depends(get_journal_service)]


@router.get("/journals", response_model=list[JournalDetailResponse])
def list_journals(
    service: JournalServiceDep, limit: int = Query(default=365, ge=1, le=365)
) -> list[JournalDetailResponse]:
    return service.list_entries(limit)


@router.get("/journal/today/context", response_model=JournalTodayContextResponse)
def get_today_journal_context(service: JournalServiceDep) -> JournalTodayContextResponse:
    return service.today()


@router.put("/journal/today", response_model=Journal)
def upsert_today_journal(request: UpsertTodayJournalRequest, service: JournalServiceDep) -> Journal:
    return service.upsert_today(request)


@router.get("/journal/{local_date}/context", response_model=JournalTodayContextResponse)
def get_journal_day_context(
    local_date: date, service: JournalServiceDep
) -> JournalTodayContextResponse:
    return service.day_context(local_date)


@router.put("/journal/{local_date}", response_model=Journal)
def upsert_journal_day(
    local_date: date, request: UpsertTodayJournalRequest, service: JournalServiceDep
) -> Journal:
    return service.upsert(request, local_date)


@router.get("/journals/{journal_id}", response_model=JournalDetailResponse)
def get_journal(journal_id: UUID, service: JournalServiceDep) -> JournalDetailResponse:
    return service.get_entry(journal_id)


@router.patch("/journals/{journal_id}", response_model=Journal)
def update_journal(
    journal_id: UUID, request: UpdateJournalRequest, service: JournalServiceDep
) -> Journal:
    return service.update(journal_id, request)


@router.post(
    "/journals/{journal_id}/media",
    response_model=JournalMedia,
    status_code=status.HTTP_201_CREATED,
)
def add_journal_media(
    journal_id: UUID, request: AddJournalMediaRequest, service: JournalServiceDep
) -> JournalMedia:
    return service.add_media(journal_id, request)


@router.delete(
    "/journals/{journal_id}/media/{media_asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_journal_media(
    journal_id: UUID, media_asset_id: UUID, service: JournalServiceDep
) -> None:
    service.remove_media(journal_id, media_asset_id)


@router.post(
    "/journals/{journal_id}/revisions",
    response_model=JournalRevision,
    status_code=status.HTTP_201_CREATED,
)
def create_journal_revision(
    journal_id: UUID,
    request: CreateJournalRevisionRequest,
    service: JournalServiceDep,
) -> JournalRevision:
    return service.add_revision(journal_id, request.content)


@router.post(
    "/journals/{journal_id}/suggestions",
    response_model=list[JournalSuggestion],
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_journal_suggestions(
    journal_id: UUID, request: GenerateJournalSuggestionsRequest
) -> list[JournalSuggestion]:
    service_not_implemented("Generate journal suggestions")


@router.post(
    "/journal-suggestions/{suggestion_id}/accept",
    response_model=JournalSuggestion,
)
def accept_journal_suggestion(suggestion_id: UUID, service: JournalServiceDep) -> JournalSuggestion:
    return service.review_suggestion(suggestion_id, accept=True)


@router.post(
    "/journal-suggestions/{suggestion_id}/reject",
    response_model=JournalSuggestion,
)
def reject_journal_suggestion(suggestion_id: UUID, service: JournalServiceDep) -> JournalSuggestion:
    return service.review_suggestion(suggestion_id, accept=False)


@router.post("/journals/{journal_id}/complete", response_model=Journal)
def complete_journal(
    journal_id: UUID, request: CompleteJournalRequest, service: JournalServiceDep
) -> Journal:
    return service.complete(journal_id, request.current_revision_id)
