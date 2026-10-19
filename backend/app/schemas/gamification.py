"""Basil totals and evidence-based mission progress."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas.base import ApiModel


class BasilTotals(ApiModel):
    today: int = 0
    lifetime: int = 0
    balance: int = 0
    competition_day: date
    day_ends_at: AwareDatetime


class MissionBatchPublic(ApiModel):
    mission_id: str
    practice_level: str
    content_version: int
    percent: int = Field(ge=0, le=100)
    status: Literal["inProgress", "review", "ready"]
    assessed_questions: int
    correct_questions: int
    total_questions: int
    independent_correct: int
    requirements: list[str] = Field(default_factory=list)


class MissionBadgePublic(ApiModel):
    mission_id: str
    name: str
    skill: str
    available: bool
    practice_level: str
    badge_level: Literal["Taster", "Cook", "Chef", "Head Chef", "Master"] | None = None
    successful_batches: int = 0
    distinct_photos: int = 0
    requirements: list[str] = Field(default_factory=list)


class GamificationSummary(ApiModel):
    policy_version: str
    basil: BasilTotals
    missions: list[MissionBadgePublic]
