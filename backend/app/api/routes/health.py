from typing import Literal

from fastapi import APIRouter

from app.schemas.base import ApiModel

router = APIRouter(tags=["health"])


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
