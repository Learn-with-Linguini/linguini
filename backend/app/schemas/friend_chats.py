"""Viewer-specific contracts for persistent two-person I-Spy conversations."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel

Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ChatCreate(ApiModel):
    command_id: UUID
    language_profile_id: UUID


class InviteToken(ApiModel):
    invite_token: Annotated[str, Field(min_length=32, max_length=100)]


class ChatJoin(ChatCreate, InviteToken):
    pass


class ChatCommand(ApiModel):
    command_id: UUID
    expected_revision: Annotated[int, Field(ge=0)]


class StartChatRound(ChatCommand):
    media_asset_id: UUID


class SelectChatTarget(ChatCommand):
    object_key: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    x: Coordinate | None = None
    y: Coordinate | None = None
    label: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    confirm: bool = False

    @model_validator(mode="after")
    def selection_is_explicit(self):
        if self.object_key is not None:
            if self.x is not None or self.y is not None or self.label is not None:
                raise ValueError("Choose an existing object or a photo location.")
        elif self.x is None or self.y is None or self.confirm:
            raise ValueError("Choose a photo location and review it before confirming.")
        return self


class SendChatClue(ChatCommand):
    text: Annotated[str, Field(min_length=1, max_length=500)]


class GuessChatTarget(ChatCommand):
    x: Coordinate
    y: Coordinate


class ReportChat(ChatCommand):
    reason: Annotated[str, Field(min_length=3, max_length=500)]


class ChatPerson(ApiModel):
    id: UUID
    display_name: str
    avatar: str | None = None
    avatar_url: str | None = None


class ChatObject(ApiModel):
    key: str
    label: str
    word: str
    translation: str
    x: Coordinate
    y: Coordinate
    width: Coordinate | None = None
    height: Coordinate | None = None


class ChatCheatSheet(ApiModel):
    mission_id: str
    practice_level: str
    content_version: int = 1


class ChatClueOption(ApiModel):
    id: str
    text: str
    translation: str
    concept: Literal["adjective", "position", "quantity", "identity"]
    cheat_sheet: ChatCheatSheet | None = None


class ChatMessage(ApiModel):
    id: UUID
    type: Literal[
        "system", "clue", "followUpClue", "guess", "incorrectResult", "correctResult", "reveal"
    ]
    sender_id: UUID | None = None
    text: str | None = None
    x: Coordinate | None = None
    y: Coordinate | None = None
    is_correct: bool | None = None
    created_at: AwareDatetime


class ChatRound(ApiModel):
    id: UUID
    sender_id: UUID
    status: Literal[
        "selectingTarget",
        "composingClue",
        "awaitingGuess",
        "awaitingFollowUp",
        "completed",
        "cancelled",
    ]
    photo_status: Literal["analyzing", "ready", "failed"]
    image_url: str | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    objects: list[ChatObject] = Field(default_factory=list)
    target: ChatObject | None = None
    clue_options: list[ChatClueOption] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    error: str | None = None
    retryable: bool = False


class ChatSnapshot(ApiModel):
    id: UUID
    status: Literal["waiting", "active", "left", "blocked"]
    revision: int
    me_id: UUID
    target_language_code: str
    viewer_level: str
    partner: ChatPerson | None
    creator: ChatPerson
    invite_status: Literal["open", "accepted", "expired", "revoked"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    active_round: ChatRound | None = None
    rounds: list[ChatRound] = Field(default_factory=list)


class ChatAccess(ApiModel):
    chat: ChatSnapshot
    invite_token: str


class InvitePreview(ApiModel):
    status: Literal["open", "full", "expired", "revoked"]
    creator: ChatPerson | None = None
    target_language_code: str | None = None


class ChatSuggestion(ApiModel):
    text: str


class ChatHelpWord(ApiModel):
    word: str
    meaning: str


class ChatHelpReference(ApiModel):
    mission_code: str
    level: str
    content_version: int = 1


class ChatHelp(ApiModel):
    explanation: str
    vocabulary: list[ChatHelpWord] = Field(default_factory=list)
    hint: str | None = None
    cheatsheet_refs: list[ChatHelpReference] = Field(default_factory=list)
