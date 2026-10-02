"""Read models for the demo progress screen."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel, EntityModel
from app.schemas.enums import XpEventType


class ScenarioProgress(ApiModel):
    scene_id: str
    session_id: UUID
    media_asset_id: UUID
    title: str
    status: Literal["in-progress", "completed", "mastered"]
    completed_task_count: Annotated[int, Field(ge=0)]
    total_task_count: Annotated[int, Field(gt=0)]
    level: str

    @model_validator(mode="after")
    def validate_counts(self) -> "ScenarioProgress":
        if self.completed_task_count > self.total_task_count:
            raise ValueError("completed tasks cannot exceed total tasks")
        return self


class LeaderboardRow(ApiModel):
    rank: Annotated[int, Field(ge=1)]
    name: str
    xp: Annotated[int, Field(ge=0)]
    is_you: bool = False


class StreakDay(ApiModel):
    date: date
    active: bool = False


class Streak(ApiModel):
    current: Annotated[int, Field(ge=0)] = 0
    days: list[StreakDay] = Field(default_factory=list)


class ProgressResponse(ApiModel):
    xp: Annotated[int, Field(ge=0)]
    scenarios: list[ScenarioProgress]
    leaderboard: list[LeaderboardRow]
    streak: Streak = Field(default_factory=Streak)


class StoredProgress(ProgressResponse):
    language_code: str = "es"
    user_id: UUID


class XpEvent(EntityModel):
    user_id: UUID
    language_profile_id: UUID | None = None
    session_id: UUID | None = None
    event_type: XpEventType
    amount: Annotated[int, Field(ge=0)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    occurred_at: AwareDatetime | None = None
