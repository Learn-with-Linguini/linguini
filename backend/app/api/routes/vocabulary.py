from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_active_language, get_learning_service
from app.api.errors import service_not_implemented
from app.schemas.base import CursorPage
from app.schemas.vocabulary import DailyVocabularyItem, DailyVocabularyResponse
from app.services.learning import LearningService

router = APIRouter(prefix="/me/vocabulary", tags=["vocabulary"])


@router.get("", response_model=CursorPage[DailyVocabularyItem])
def list_vocabulary(
    service: Annotated[LearningService, Depends(get_learning_service)],
    language: Annotated[str, Depends(get_active_language)],
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> CursorPage[DailyVocabularyItem]:
    return service.list_vocabulary(cursor, limit, language)


@router.get("/daily", response_model=DailyVocabularyResponse)
async def get_daily_vocabulary(local_date: date | None = None) -> DailyVocabularyResponse:
    service_not_implemented("Get daily vocabulary")


@router.get("/{vocabulary_item_id}", response_model=DailyVocabularyItem)
async def get_vocabulary_item(vocabulary_item_id: UUID) -> DailyVocabularyItem:
    service_not_implemented("Get learner vocabulary item")
