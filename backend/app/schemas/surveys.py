"""Schemas for learner satisfaction and feedback surveys."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel


class CreateSurveyRequest(ApiModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    usage_frequency: Annotated[str, Field(default="", max_length=2000)] = ""
    motivation: Annotated[str, Field(default="", max_length=2000)] = ""
    improvements: Annotated[str, Field(default="", max_length=2000)] = ""
    receive_follow_up: bool = False
    email: Annotated[str | None, Field(default=None, max_length=320)] = None
    trigger_source: Annotated[str, Field(default="profile", max_length=32)] = "profile"
    lesson_count: int | None = None


class SurveyResponse(ApiModel):
    id: UUID
    user_id: UUID | None = None
    email: str | None = None
    rating: int
    usage_frequency: str
    motivation: str
    improvements: str
    receive_follow_up: bool
    trigger_source: str
    lesson_count: int | None = None
    created_at: datetime
