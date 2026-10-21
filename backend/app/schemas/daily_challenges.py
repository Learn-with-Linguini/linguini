"""Today's photo challenge, its live word counts, and the learner's last payout."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.base import ApiModel


class DailyChallengeWord(ApiModel):
    label: str
    count: Annotated[int, Field(ge=1)]
    found_by_you: bool


class DailyChallengeResult(ApiModel):
    challenge_day: date
    scene_title: str
    rank: Annotated[int, Field(ge=1)]
    participant_count: Annotated[int, Field(ge=1)]
    basil: Annotated[int, Field(ge=1)]


class DailyChallengeResponse(ApiModel):
    challenge_day: date
    scene_key: str
    scene_title: str
    # e.g. "at the library", for "Spot a word at the library".
    scene_phrase: str
    day_ends_at: AwareDatetime
    status: Literal["notStarted", "inProgress", "completed"]
    session_id: UUID | None = None
    participant_count: Annotated[int, Field(ge=0)]
    joined_count: Annotated[int, Field(ge=0)]
    words: list[DailyChallengeWord]
    your_word_count: Annotated[int, Field(ge=0)]
    last_result: DailyChallengeResult | None = None
