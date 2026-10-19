"""Optional daily recognition, separate from spendable Basil and proficiency."""

from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, Field

from app.schemas.base import ApiModel
from app.schemas.users import PastaAvatar


class ChefLeaderboardPreference(ApiModel):
    participating: Annotated[bool, Field(strict=True)]


class ChefLeaderboardEntry(ApiModel):
    rank: Annotated[int, Field(ge=1)]
    display_name: str
    basil: Annotated[int, Field(ge=1)]
    avatar: PastaAvatar = "farfalle"


class ChefLeaderboardResponse(ApiModel):
    participating: bool
    competition_day: date
    day_ends_at: AwareDatetime
    today_basil: Annotated[int, Field(ge=0)]
    personal_best: Annotated[int, Field(ge=0)]
    current_rank: Annotated[int, Field(ge=1)] | None = None
    basil_to_next_rank: Annotated[int, Field(ge=1)] | None = None
    top: list[ChefLeaderboardEntry]
