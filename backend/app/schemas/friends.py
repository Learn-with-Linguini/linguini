"""Private friendship invitations and compatible learning profiles."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.base import ApiModel


class FriendInviteRequest(ApiModel):
    command_id: UUID


class FriendAcceptRequest(FriendInviteRequest):
    invite_code: Annotated[str, Field(min_length=32, max_length=100)]


class FriendInvite(ApiModel):
    invite_code: str
    expires_at: AwareDatetime


class FriendPublic(ApiModel):
    user_id: UUID
    display_name: str
    source_language_code: str | None = None
    target_language_code: str | None = None
    proficiency_level: str | None = None
    can_challenge: bool = False
