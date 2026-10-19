"""Authenticated mission progress and account-wide Basil totals."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.api.auth import get_current_user_id
from app.repositories.postgres.game_resources import lock_resource_owner
from app.repositories.postgres.gamification import gamification_summary, session_missions
from app.repositories.postgres.language_profiles import language_profiles
from app.schemas.gamification import GamificationSummary, MissionBatchPublic

router = APIRouter(tags=["gamification"])
UserDep = Annotated[UUID, Depends(get_current_user_id)]


@router.get("/me/gamification", response_model=GamificationSummary)
def get_gamification(
    request: Request,
    user_id: UserDep,
    language_profile_id: Annotated[UUID | None, Query(alias="languageProfileId")] = None,
):
    with request.app.state.database_engine.begin() as c:
        lock_resource_owner(c, user_id)
        query = select(language_profiles).where(language_profiles.c.user_id == user_id)
        query = (
            query.where(language_profiles.c.id == language_profile_id)
            if language_profile_id
            else query.where(language_profiles.c.is_active.is_(True))
        )
        profile = c.execute(query).mappings().first()
        if profile is None:
            raise HTTPException(
                404, detail={"code": "profile_not_found", "message": "Learning profile not found."}
            )
        return gamification_summary(c, user_id, profile)


@router.get("/sessions/{session_id}/mission-progress", response_model=list[MissionBatchPublic])
def get_mission_progress(session_id: UUID, request: Request, user_id: UserDep):
    with request.app.state.database_engine.connect() as c:
        result = session_missions(c, user_id, session_id)
        if result is None:
            raise HTTPException(
                404, detail={"code": "session_not_found", "message": "Session not found."}
            )
        return result
