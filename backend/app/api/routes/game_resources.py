from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth import get_current_user_id
from app.repositories.postgres.game_resources import (
    equip_appearance,
    game_resources_enabled,
    lock_resource_owner,
    resource_snapshot,
)
from app.schemas.game_resources import AppearanceRequest, GameResourcesResponse

router = APIRouter(prefix="/me/game-resources", tags=["game resources"])


def require_game_resources() -> None:
    if not game_resources_enabled():
        raise HTTPException(404, detail={"code": "feature_disabled", "message": "Unavailable."})


@router.get(
    "", response_model=GameResourcesResponse, dependencies=[Depends(require_game_resources)]
)
def get_resources(request: Request, user_id: Annotated[UUID, Depends(get_current_user_id)]):
    with request.app.state.database_engine.begin() as connection:
        lock_resource_owner(connection, user_id)
        return resource_snapshot(connection, user_id)


@router.post("/appearance", response_model=GameResourcesResponse,
             dependencies=[Depends(require_game_resources)])
def set_appearance(
    body: AppearanceRequest, request: Request,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
):
    with request.app.state.database_engine.begin() as connection:
        lock_resource_owner(connection, user_id)
        return equip_appearance(connection, user_id, body.appearance, body.command_id)
