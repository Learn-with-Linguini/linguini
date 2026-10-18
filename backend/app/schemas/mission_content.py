"""Public, learner-facing snapshots used by deterministic mission lessons."""

from typing import Literal
from uuid import UUID

from app.schemas.base import ApiModel


class TaughtChunk(ApiModel):
    text: str
    translation: str


class A0MissionSnapshot(ApiModel):
    mission_id: Literal["M04", "M05"]
    level: Literal["A0"] = "A0"
    situation: Literal["lostAndFound", "everydayChoice"]
    taught_chunks: list[TaughtChunk]
    owned_object_id: UUID | None = None
    pretend: bool | None = None
    preference_object_ids: list[UUID] | None = None
    chosen_object_id: UUID | None = None
    reaction: Literal["like", "dislike"] | None = None
