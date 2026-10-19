from datetime import datetime
from typing import Literal
from uuid import UUID

from app.schemas.base import ApiModel

Appearance = Literal["default", "herb", "pasta"]


class SauceBalance(ApiModel):
    remaining: int
    capacity: int
    refills_at: datetime


class GameResourcesResponse(ApiModel):
    energy_gate_enabled: Literal[False] = False
    sauce: SauceBalance
    basil_leaves: int
    appearance: Appearance
    owned_appearances: list[Appearance]


class AppearanceRequest(ApiModel):
    appearance: Appearance
    command_id: UUID


