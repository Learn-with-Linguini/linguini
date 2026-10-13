"""Public room contracts deliberately exclude private scene/turn snapshots."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_serializer

from app.schemas.base import ApiModel


class CreateRoomRequest(ApiModel):
    command_id: UUID
    language_profile_id: UUID


class JoinRoomRequest(CreateRoomRequest):
    invite_code: Annotated[str, Field(min_length=32, max_length=100)]


class RoomCommand(ApiModel):
    command_id: UUID
    expected_revision: Annotated[int, Field(ge=0)]


class AddRoomPhotoRequest(RoomCommand):
    media_asset_id: UUID


class RoomReadyRequest(RoomCommand):
    ready: bool = True


class RoomClueRequest(RoomCommand):
    clue_option_id: Annotated[str, Field(min_length=1, max_length=100)]


class RoomGuessRequest(RoomCommand):
    object_key: Annotated[str, Field(min_length=1, max_length=100)]


class PhotoReviewObject(ApiModel):
    key: Annotated[str, Field(min_length=1, max_length=100)]
    label: Annotated[str, Field(min_length=1, max_length=100)]
    x: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    color: Annotated[str, Field(max_length=40)] | None = None


class PhotoReviewRelation(ApiModel):
    key: Annotated[str, Field(min_length=1, max_length=100)]
    subject_object_key: str
    relation: Literal[
        "left_of",
        "right_of",
        "above",
        "below",
        "on",
        "under",
        "inside",
        "in_front_of",
        "behind",
        "next_to",
        "near",
    ]
    reference_object_key: str


class RoomPhotoReview(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    objects: Annotated[list[PhotoReviewObject], Field(min_length=2, max_length=6)]
    relations: Annotated[list[PhotoReviewRelation], Field(max_length=20)] = []


class ReviewRoomPhotoRequest(RoomCommand):
    review: RoomPhotoReview


class RoomObject(ApiModel):
    key: str
    label: str
    word: str
    translation: str
    x: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    marker: int


class RoomClueOption(ApiModel):
    id: str
    text: str


class RoomMemberPublic(ApiModel):
    user_id: UUID
    display_name: str
    seat: int
    ready: bool
    acknowledged: bool = False


class RoomPhotoPublic(ApiModel):
    id: UUID
    owner_user_id: UUID | None
    media_asset_id: UUID | None
    status: Literal["queued", "analyzing", "awaitingReview", "preparing", "ready", "failed"]
    image_url: str | None = None
    review: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    processing: bool = False


class RoomTurnResult(ApiModel):
    is_correct: bool
    target_object_key: str
    message: str


class RoomTurnPublic(ApiModel):
    id: UUID
    index: int
    role: Literal["sender", "guesser"]
    phase: Literal["compose", "guess", "reveal"]
    photo_id: UUID
    image_url: str
    objects: list[RoomObject]
    clue: str | None = None
    target_object_key: str | None = None
    clue_options: list[RoomClueOption] | None = None
    guess_count: int = 0
    guessed_object_keys: list[str] = []
    result: RoomTurnResult | None = None


class RoomContributionPublic(ApiModel):
    user_id: UUID
    clues_sent: int = 0
    guesses_made: int = 0
    correct_guesses: int = 0
    basil_earned: int = 0
    xp_earned: int = 0


class RoomSnapshot(ApiModel):
    id: UUID
    status: Literal["lobby", "playing", "completed", "ended", "expired"]
    revision: int
    expires_at: AwareDatetime
    me_id: UUID
    host_user_id: UUID | None
    source_language_code: str
    target_language_code: str
    proficiency_level: str
    members: list[RoomMemberPublic]
    photos: list[RoomPhotoPublic]
    current_turn: RoomTurnPublic | None = None
    successful_rounds: int = 0
    round_count: int = 0
    contributions: list[RoomContributionPublic]
    invite_code: str | None = None

    @model_serializer(mode="wrap")
    def hide_unavailable_invite(self, handler):
        data = handler(self)
        if self.invite_code is None:
            data.pop("inviteCode", None)
            data.pop("invite_code", None)
        return data


class RoomAccessResponse(ApiModel):
    room: RoomSnapshot
    invite_code: str | None = None
