from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.auth import get_current_user_id
from app.repositories.postgres.game_resources import (
    equip_appearance,
    lock_resource_owner,
    resource_snapshot,
)
from app.schemas.game_resources import AppearanceRequest, GameResourcesResponse

router = APIRouter(prefix="/me/game-resources", tags=["game resources"])


@router.get("", response_model=GameResourcesResponse)
def get_resources(request: Request, user_id: Annotated[UUID, Depends(get_current_user_id)]):
    with request.app.state.database_engine.begin() as connection:
        lock_resource_owner(connection, user_id)
        return resource_snapshot(connection, user_id)


@router.post("/appearance", response_model=GameResourcesResponse)
def set_appearance(
    body: AppearanceRequest, request: Request,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
):
    with request.app.state.database_engine.begin() as connection:
        lock_resource_owner(connection, user_id)
        return equip_appearance(connection, user_id, body.appearance, body.command_id)
