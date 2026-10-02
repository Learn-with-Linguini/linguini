"""User and language-profile schemas."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from app.schemas.base import ApiModel, EntityModel, LanguageCode, NonEmptyText
from app.schemas.enums import PreferredInputMode, ProficiencyLevel


def _validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


class User(EntityModel):
    learning_goal: Annotated[str, Field(max_length=300)] = ""
    microphone_enabled: bool = True
    camera_enabled: bool = True
    auth_provider_id: NonEmptyText
    display_name: Annotated[str, Field(min_length=1, max_length=100)]
    email: Annotated[str, Field(max_length=320)] | None = None
    timezone: str = "UTC"
    onboarding_completed: bool = False

    _timezone_is_valid = field_validator("timezone")(_validate_timezone)


class UpdateUserRequest(ApiModel):
    learning_goal: Annotated[str, Field(max_length=300)] | None = None
    microphone_enabled: bool | None = None
    camera_enabled: bool | None = None
    display_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    timezone: str | None = None
    onboarding_completed: bool | None = None

    _timezone_is_valid = field_validator("timezone")(_validate_timezone)


class LanguageProfile(EntityModel):
    user_id: UUID
    source_language_code: LanguageCode
    target_language_code: LanguageCode
    proficiency_level: ProficiencyLevel
    is_active: bool = True
    preferred_input_mode: PreferredInputMode = PreferredInputMode.BOTH
    daily_goal_minutes: Annotated[int, Field(ge=1, le=240)] | None = None

    @model_validator(mode="after")
    def languages_must_differ(self) -> LanguageProfile:
        if self.source_language_code.lower() == self.target_language_code.lower():
            raise ValueError("source and target languages must be different")
        return self


class CreateLanguageProfileRequest(ApiModel):
    source_language_code: LanguageCode
    target_language_code: LanguageCode
    proficiency_level: ProficiencyLevel
    preferred_input_mode: PreferredInputMode = PreferredInputMode.BOTH
    daily_goal_minutes: Annotated[int, Field(ge=1, le=240)] | None = None

    @model_validator(mode="after")
    def languages_must_differ(self) -> CreateLanguageProfileRequest:
        if self.source_language_code.lower() == self.target_language_code.lower():
            raise ValueError("source and target languages must be different")
        return self


class UpdateLanguageProfileRequest(ApiModel):
    proficiency_level: ProficiencyLevel | None = None
    preferred_input_mode: PreferredInputMode | None = None
    daily_goal_minutes: Annotated[int, Field(ge=1, le=240)] | None = None
    is_active: bool | None = None
