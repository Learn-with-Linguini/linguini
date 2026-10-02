from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_active_language, get_learning_service
from app.schemas.progress import ProgressResponse
from app.services.learning import LearningService

router = APIRouter(tags=["progress"])


@router.get("/me/progress", response_model=ProgressResponse)
def get_progress(
    service: Annotated[LearningService, Depends(get_learning_service)],
    language: Annotated[str, Depends(get_active_language)],
) -> ProgressResponse:
    return service.get_progress(language)
