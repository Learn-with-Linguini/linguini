"""Aggregated home-screen response schema."""

from typing import Annotated

from pydantic import Field

from app.schemas.base import ApiModel
from app.schemas.journals import Journal
from app.schemas.sessions import Session


class DailyHomeProgress(ApiModel):
    completed_task_count: Annotated[int, Field(ge=0)] = 0
    skipped_task_count: Annotated[int, Field(ge=0)] = 0
    learned_word_count: Annotated[int, Field(ge=0)] = 0


class HomeResponse(ApiModel):
    active_session: Session | None = None
    today_journal: Journal | None = None
    daily_progress: DailyHomeProgress = Field(default_factory=DailyHomeProgress)
