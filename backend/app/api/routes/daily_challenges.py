"""Authenticated daily photo challenge and its live word counts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import get_current_user_id
from app.repositories.postgres.daily_challenges import challenge_snapshot, settle_finished_days
from app.schemas.daily_challenges import DailyChallengeResponse

router = APIRouter(prefix="/me/daily-challenge", tags=["gamification"])
UserDep = Annotated[UUID, Depends(get_current_user_id)]


@router.get("", response_model=DailyChallengeResponse)
def get_daily_challenge(request: Request, user_id: UserDep):
    try:
        engine = request.app.state.database_engine
        # Settle finished days first so yesterday's payout shows with today's scene.
        with engine.begin() as connection:
            settle_finished_days(connection)
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ",
        ) as connection, connection.begin():
            return challenge_snapshot(connection, user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={
            "code": "daily_challenge_unavailable",
            "message": "The daily challenge is unavailable right now. Please try again.",
        }) from exc
