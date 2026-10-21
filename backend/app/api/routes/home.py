from fastapi import APIRouter

from app.api.errors import service_not_implemented
from app.schemas.home import HomeResponse

router = APIRouter(tags=["home"])


@router.get("/home", response_model=HomeResponse)
async def get_home() -> HomeResponse:
    service_not_implemented("Get home summary")
