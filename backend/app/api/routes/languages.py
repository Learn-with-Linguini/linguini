"""Public language registry endpoint."""

from fastapi import APIRouter

from app.languages import languages
from app.schemas.languages import LanguageListResponse

router = APIRouter(tags=["languages"])


@router.get("/languages", response_model=LanguageListResponse)
async def list_languages() -> LanguageListResponse:
    return LanguageListResponse(items=languages())
