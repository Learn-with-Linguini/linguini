"""Authenticated daily Chef of the Day standings."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import get_current_user_id
from app.repositories.postgres.game_resources import lock_resource_owner
from app.repositories.postgres.leaderboard import leaderboard_snapshot
from app.schemas.leaderboard import ChefLeaderboardResponse

router = APIRouter(prefix="/me/chef-of-the-day", tags=["gamification"])
UserDep = Annotated[UUID, Depends(get_current_user_id)]


def _run(request, user_id):
    try:
        with request.app.state.database_engine.connect().execution_options(
            isolation_level="REPEATABLE READ",
        ) as connection, connection.begin():
            lock_resource_owner(connection, user_id)
            return leaderboard_snapshot(connection, user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={
            "code": "chef_leaderboard_unavailable",
            "message": "Chef of the Day is unavailable right now. Please try again.",
        }) from exc


@router.get("", response_model=ChefLeaderboardResponse)
def get_leaderboard(request: Request, user_id: UserDep):
    return _run(request, user_id)
