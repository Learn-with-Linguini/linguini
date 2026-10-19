from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_ispy_game_service
from app.schemas.ispy import ISpyPhotoPage, StartISpyGameRequest
from app.schemas.sessions import SessionDetailResponse
from app.services.ispy_games import ISpyGameService

router = APIRouter(prefix="/ispy", tags=["ispy"])

ISpyGameServiceDep = Annotated[ISpyGameService, Depends(get_ispy_game_service)]


@router.get("/photos", response_model=ISpyPhotoPage)
def list_ispy_photos(
    service: ISpyGameServiceDep,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> ISpyPhotoPage:
    return service.photos(cursor)


@router.get("/games/active", response_model=SessionDetailResponse | None)
def get_active_ispy_game(service: ISpyGameServiceDep) -> SessionDetailResponse | None:
    return service.active()


@router.post(
    "/games",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_ispy_game(
    request: StartISpyGameRequest, service: ISpyGameServiceDep
) -> SessionDetailResponse:
    return service.start(request)
