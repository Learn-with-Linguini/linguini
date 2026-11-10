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
    """Start a round with a new owned photo, or continue on a finished round's photo."""

    media_asset_id: UUID | None = None
    source_round_id: UUID | None = None

    @model_validator(mode="after")
    def one_photo_source(self):
        if (self.media_asset_id is None) == (self.source_round_id is None):
            raise ValueError("Choose a new photo or continue on the previous photo.")
        return self


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


ReviewRelationName = Literal[
    "left_of", "right_of", "above", "below", "on", "under", "inside",
    "in_front_of", "behind", "next_to", "near",
]
ReviewAttributeName = Literal["color", "size", "shape", "material", "pattern", "state"]
ObjectKey = Annotated[str, Field(min_length=1, max_length=100)]
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
AddedObjectKey = Annotated[str, Field(pattern=rf"^added-{_UUID}$")]


class ChatAddedObject(ApiModel):
    key: AddedObjectKey
    label: Annotated[str, Field(min_length=1, max_length=60)]
    x: Coordinate
    y: Coordinate


class ChatMovedObject(ApiModel):
    key: ObjectKey
    x: Coordinate
    y: Coordinate


class ChatReviewRelationInput(ApiModel):
    subject_object_key: ObjectKey
    relation: ReviewRelationName
    reference_object_key: ObjectKey


class ConfirmChatObjects(ChatCommand):
    """The sender's review of the analyzed objects, as in practice scene review."""

    accepted_object_keys: Annotated[list[ObjectKey], Field(max_length=20)]
    added_objects: Annotated[list[ChatAddedObject], Field(max_length=20)] = Field(
        default_factory=list
    )
    moved_objects: Annotated[list[ChatMovedObject], Field(max_length=40)] = Field(
        default_factory=list
    )
    object_attributes: dict[
        ObjectKey, dict[ReviewAttributeName, Annotated[str, Field(max_length=60)]]
    ] = Field(default_factory=dict)
    relations: Annotated[list[ChatReviewRelationInput], Field(max_length=100)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def consistent_review(self):
        keys = self.accepted_object_keys + [item.key for item in self.added_objects]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("Keep at least one object, with no duplicates.")
        if any(not item.label.strip() for item in self.added_objects):
            raise ValueError("Name each object you add.")
        selected = set(keys)
        moved = [item.key for item in self.moved_objects]
        if len(moved) != len(set(moved)) or not set(moved) <= set(self.accepted_object_keys):
            raise ValueError("Move each kept object at most once.")
        if not set(self.object_attributes) <= selected:
            raise ValueError("Adjectives must belong to kept objects.")
        triples = set()
        for row in self.relations:
            if row.subject_object_key == row.reference_object_key:
                raise ValueError("A relation connects two different objects.")
            if not {row.subject_object_key, row.reference_object_key} <= selected:
                raise ValueError("Relations must connect kept objects.")
            triple = (row.subject_object_key, row.relation, row.reference_object_key)
            if triple in triples:
                raise ValueError("Each relation can appear once.")
            triples.add(triple)
        return self


class ChatReviewObject(ApiModel):
    key: str
    label: str
    x: Coordinate
    y: Coordinate
    attributes: dict[str, str] = Field(default_factory=dict)


class ChatReviewRelation(ApiModel):
    key: str
    subject_object_key: str
    relation: str
    reference_object_key: str


class GuessChatTarget(ChatCommand):
    """A guess names one of the round's marked choices, or (older clients) a photo point."""

    choice_key: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    x: Coordinate | None = None
    y: Coordinate | None = None

    @model_validator(mode="after")
    def one_guess(self):
        point = self.x is not None and self.y is not None
        if self.choice_key is not None:
            if self.x is not None or self.y is not None:
                raise ValueError("Choose a marked object or a photo location, not both.")
        elif not point:
            raise ValueError("Choose one of the marked objects.")
        return self


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


class ChatGuessChoice(ApiModel):
    """One marked object the guesser may pick. The key is opaque and per round.

    Every choice carries its own name, so showing the tapped one reveals nothing
    about which choice is the target.
    """

    key: str
    x: Coordinate
    y: Coordinate
    width: Coordinate | None = None
    height: Coordinate | None = None
    word: str = ""
    # Only when both players share an explanation language; otherwise omitted.
    translation: str | None = None


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
        "reviewingObjects",
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
    # Every marked object, target included, in an order that does not reveal it.
    guess_choices: list[ChatGuessChoice] = Field(default_factory=list)
    # The sender's unconfirmed analysis while the round is reviewingObjects.
    review_objects: list[ChatReviewObject] = Field(default_factory=list)
    review_relations: list[ChatReviewRelation] = Field(default_factory=list)
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
    # Who starts the next round: the player who guessed in the last finished round.
    # None means either player may start (no round has finished yet).
    next_sender_id: UUID | None = None
    # A finished round whose photo this viewer may reuse for their next round.
    reusable_photo_round_id: UUID | None = None


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
