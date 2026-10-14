"""Durable two-person rooms. All game authority lives in PostgreSQL."""

import hashlib
import json
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.users import users
from app.repositories.postgres.xp import award
from app.schemas.base import utc_now
from app.schemas.media import MediaAsset
from app.schemas.rooms import (
    RoomAccessResponse,
    RoomContributionPublic,
    RoomMemberPublic,
    RoomPhotoPublic,
    RoomSnapshot,
    RoomTurnPublic,
)

metadata = MetaData()


def _id():
    return Column("id", Uuid, primary_key=True)


def _time(name, nullable=False):
    return Column(name, DateTime(timezone=True), nullable=nullable)


learning_rooms = Table(
    "learning_rooms",
    metadata,
    _id(),
    Column("host_user_id", Uuid),
    Column("source_language_code", String(35), nullable=False),
    Column("target_language_code", String(35), nullable=False),
    Column("proficiency_level", String(2), nullable=False),
    Column("status", String(16), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("invite_hash", String(64), nullable=False),
    Column("invite_code", String(64)),
    _time("invite_expires_at"),
    _time("expires_at"),
    _time("ended_at", True),
    _time("created_at"),
    _time("updated_at"),
    schema="public",
)
room_members = Table(
    "room_members",
    metadata,
    _id(),
    Column("room_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid),
    Column("seat", Integer, nullable=False),
    Column("ready", Boolean, nullable=False),
    Column("active", Boolean, nullable=False),
    _time("joined_at"),
    schema="public",
)
room_photos = Table(
    "room_photos",
    metadata,
    _id(),
    Column("room_id", Uuid, nullable=False),
    Column("owner_user_id", Uuid),
    Column("media_asset_id", Uuid),
    Column("status", String(20), nullable=False),
    Column("moderation_passed", Boolean, nullable=False),
    Column("content_hash", String(64)),
    Column("analysis", JSONB),
    Column("review", JSONB),
    Column("pack", JSONB),
    Column("processing_claim_id", Uuid),
    _time("claim_expires_at", True),
    Column("analysis_attempts", Integer, nullable=False),
    Column("preparation_attempts", Integer, nullable=False),
    Column("error_code", String(60)),
    Column("error_message", String(300)),
    Column("retryable", Boolean, nullable=False),
    _time("created_at"),
    _time("updated_at"),
    schema="public",
)
room_turns = Table(
    "room_turns",
    metadata,
    _id(),
    Column("room_id", Uuid, nullable=False),
    Column("photo_id", Uuid),
    Column("turn_index", Integer, nullable=False),
    Column("sender_user_id", Uuid),
    Column("guesser_user_id", Uuid),
    Column("phase", String(16), nullable=False),
    Column("target_object_key", String(100)),
    Column("clue_option_id", String(100)),
    Column("clue", Text),
    Column("guessed_object_keys", JSONB, nullable=False),
    Column("is_correct", Boolean),
    _time("created_at"),
    _time("resolved_at", True),
    schema="public",
)
room_commands = Table(
    "room_commands",
    metadata,
    _id(),
    Column("room_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("command_id", Uuid, nullable=False),
    Column("kind", String(80), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    _time("created_at"),
    schema="public",
)
room_contributions = Table(
    "room_contributions",
    metadata,
    _id(),
    Column("room_id", Uuid, nullable=False),
    Column("turn_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("clue_sent", Boolean, nullable=False),
    Column("guess_count", Integer, nullable=False),
    Column("correct_guess", Boolean, nullable=False),
    Column("acknowledged", Boolean, nullable=False),
    Column("basil_earned", Integer, nullable=False),
    Column("xp_earned", Integer, nullable=False),
    _time("created_at"),
    _time("updated_at"),
    schema="public",
)

LIVE = {"lobby", "playing"}
LOBBY_DURATION = timedelta(minutes=30)
INVITE_DURATION = timedelta(minutes=10)
PLAY_DURATION = timedelta(minutes=30)
PHOTO_LEASE = timedelta(minutes=8)


class RoomError(Exception):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class RoomUnavailableError(RoomError):
    def __init__(self):
        super().__init__("room_unavailable", "Playing with a friend is unavailable right now.", 503)


@dataclass(frozen=True)
class RoomPhotoJob:
    photo_id: UUID
    room_id: UUID
    owner_user_id: UUID
    claim_id: UUID
    phase: str
    asset: MediaAsset
    profile: dict
    analysis: dict | None
    review: dict | None


def _fingerprint(kind, request):
    encoded = json.dumps(
        {"kind": kind, "body": request.model_dump(mode="json", by_alias=True)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _image_url(room_id, photo_id):
    return f"/api/v1/rooms/{room_id}/photos/{photo_id}/image?width=640"


def _effective_status(room):
    if room["status"] in LIVE and room["expires_at"] <= utc_now():
        return "expired"
    return room["status"]


def cleanup_room_account(c, user_id):
    """Caller holds its account user lock. Never acquire partner/resource locks here."""
    ids = list(
        c.execute(select(room_members.c.room_id).where(room_members.c.user_id == user_id)).scalars()
    )
    if not ids:
        return
    c.execute(
        select(learning_rooms.c.id)
        .where(learning_rooms.c.id.in_(ids))
        .order_by(learning_rooms.c.id)
        .with_for_update()
    ).all()
    now = utc_now()
    c.execute(update(learning_rooms).where(learning_rooms.c.id.in_(ids)).values(
        invite_code=None, invite_expires_at=now,
    ))
    c.execute(
        update(learning_rooms)
        .where(
            learning_rooms.c.id.in_(ids),
            learning_rooms.c.status.in_(LIVE),
        )
        .values(
            status="ended",
            ended_at=now,
            updated_at=now,
            revision=learning_rooms.c.revision + 1,
            invite_expires_at=now,
        )
    )
    c.execute(update(room_members).where(room_members.c.room_id.in_(ids)).values(active=False))
    owned = list(
        c.execute(
            select(room_photos.c.id).where(
                room_photos.c.owner_user_id == user_id,
            )
        ).scalars()
    )
    if owned:
        c.execute(
            update(room_turns)
            .where(room_turns.c.photo_id.in_(owned))
            .values(
                target_object_key=None,
                clue=None,
                clue_option_id=None,
                guessed_object_keys=[],
            )
        )
        c.execute(
            update(room_photos)
            .where(room_photos.c.id.in_(owned))
            .values(
                media_asset_id=None,
                owner_user_id=None,
                content_hash=None,
                analysis=None,
                review=None,
                pack=None,
                status="failed",
                moderation_passed=False,
                processing_claim_id=None,
                claim_expires_at=None,
                error_code="room_photo_removed",
                retryable=False,
                error_message="This photo is no longer available.",
                updated_at=now,
            )
        )


class PostgresRoomRepository:
    def __init__(self, engine, user_id, *, spend_sauce=None, reward_basil=None):
        self.engine, self.user_id = engine, user_id
        self.spend_sauce, self.reward_basil = spend_sauce, reward_basil

    @contextmanager
    def _locked(self, room_id=None):
        """Users sorted first, then rooms sorted; recheck membership after locking."""
        try:
            with self.engine.begin() as c:
                room_ids = set(
                    c.execute(
                        select(room_members.c.room_id).where(
                            room_members.c.user_id == self.user_id,
                            room_members.c.active.is_(True),
                        )
                    ).scalars()
                )
                if room_id:
                    room_ids.add(room_id)
                owner_ids = (
                    set(
                        c.execute(
                            select(room_members.c.user_id).where(
                                room_members.c.room_id.in_(room_ids),
                            )
                        ).scalars()
                    )
                    if room_ids
                    else set()
                )
                owner_ids.add(self.user_id)
                locked_users = set(
                    c.execute(
                        select(users.c.id)
                        .where(users.c.id.in_(owner_ids))
                        .order_by(users.c.id)
                        .with_for_update()
                    ).scalars()
                )
                if self.user_id not in locked_users:
                    raise RoomError("room_unauthenticated", "Sign in to play with a friend.", 401)
                if room_ids:
                    c.execute(
                        select(learning_rooms.c.id)
                        .where(learning_rooms.c.id.in_(room_ids))
                        .order_by(learning_rooms.c.id)
                        .with_for_update()
                    ).all()
                    current_ids = set(
                        c.execute(
                            select(room_members.c.user_id).where(
                                room_members.c.room_id.in_(room_ids),
                            )
                        ).scalars()
                    )
                    if not current_ids <= locked_users:
                        raise RoomError("room_conflict", "The room changed. Refresh and try again.")
                    now = utc_now()
                    expired = list(
                        c.execute(
                            select(learning_rooms.c.id).where(
                                learning_rooms.c.id.in_(room_ids),
                                learning_rooms.c.status.in_(LIVE),
                                learning_rooms.c.expires_at <= now,
                            )
                        ).scalars()
                    )
                    if expired:
                        c.execute(
                            update(learning_rooms)
                            .where(learning_rooms.c.id.in_(expired))
                            .values(
                                status="expired",
                                invite_code=None,
                                invite_expires_at=now,
                                ended_at=now,
                                updated_at=now,
                                revision=learning_rooms.c.revision + 1,
                            )
                        )
                        c.execute(
                            update(room_members)
                            .where(room_members.c.room_id.in_(expired))
                            .values(active=False)
                        )
                    c.execute(update(learning_rooms).where(
                        learning_rooms.c.id.in_(room_ids),
                        learning_rooms.c.invite_code.is_not(None),
                        self._stale_invitation(now),
                    ).values(invite_code=None))
                yield c
        except SQLAlchemyError as exc:
            raise RoomError(
                "room_storage_error", "The room could not be saved. Try again.", 503
            ) from exc

    def _room(self, c, room_id):
        room = (
            c.execute(select(learning_rooms).where(learning_rooms.c.id == room_id))
            .mappings()
            .first()
        )
        if room is None:
            raise RoomError("room_not_found", "Room not found.", 404)
        return dict(room)

    def _members(self, c, room_id):
        return [
            dict(row)
            for row in c.execute(
                select(room_members, users.c.display_name)
                .join(users, users.c.id == room_members.c.user_id)
                .where(room_members.c.room_id == room_id)
                .order_by(room_members.c.seat)
            ).mappings()
        ]

    def _member(self, c, room_id, *, active=False):
        row = (
            c.execute(
                select(room_members).where(
                    room_members.c.room_id == room_id,
                    room_members.c.user_id == self.user_id,
                )
            )
            .mappings()
            .first()
        )
        if row is None or (active and not row["active"]):
            raise RoomError("room_not_found", "Room not found.", 404)
        return dict(row)

    def _profile(self, c, profile_id):
        row = (
            c.execute(
                select(language_profiles).where(
                    language_profiles.c.id == profile_id,
                    language_profiles.c.user_id == self.user_id,
                    language_profiles.c.is_active.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RoomError("room_profile_invalid", "Choose your active learning language.", 422)
        if (
            row["source_language_code"].lower() != "en"
            or row["target_language_code"].lower() not in {"es", "fr"}
            or row["proficiency_level"] not in {"A1", "A2"}
        ):
            raise RoomError(
                "room_language_unsupported",
                "Photo rooms support A1/A2 English to Spanish or French.",
                422,
            )
        return dict(row)

    def _setup_rate(self, c):
        recent = c.execute(
            select(func.count())
            .select_from(room_members)
            .where(
                room_members.c.user_id == self.user_id,
                room_members.c.joined_at > utc_now() - timedelta(hours=1),
            )
        ).scalar_one()
        if recent >= 5:
            raise RoomError(
                "room_rate_limited", "You've opened several rooms. Try again later.", 429
            )

    def _no_active_room(self, c, except_room=None):
        query = select(room_members.c.room_id).where(
            room_members.c.user_id == self.user_id,
            room_members.c.active.is_(True),
        )
        if except_room:
            query = query.where(room_members.c.room_id != except_room)
        if c.execute(query).first():
            raise RoomError(
                "room_already_active", "Leave your current room before joining another."
            )

    def _remembered(self, c, room_id, kind, request):
        row = (
            c.execute(
                select(room_commands).where(
                    room_commands.c.room_id == room_id,
                    room_commands.c.user_id == self.user_id,
                    room_commands.c.command_id == request.command_id,
                )
            )
            .mappings()
            .first()
        )
        if row:
            if row["kind"] != kind or row["fingerprint"] != _fingerprint(kind, request):
                raise RoomError(
                    "room_command_conflict", "This action key was used for a different action."
                )
            return True
        return False

    def _remember(self, c, room_id, kind, request):
        c.execute(
            insert(room_commands).values(
                id=uuid4(),
                room_id=room_id,
                user_id=self.user_id,
                command_id=request.command_id,
                kind=kind,
                fingerprint=_fingerprint(kind, request),
                created_at=utc_now(),
            )
        )

    def _check_command(self, c, room_id, kind, request, status=None):
        self._member(c, room_id)
        room = self._room(c, room_id)
        if self._remembered(c, room_id, kind, request):
            return room, True
        if _effective_status(room) not in LIVE:
            raise RoomError("room_not_active", "This room has ended.")
        self._member(c, room_id, active=True)
        if request.expected_revision != room["revision"]:
            raise RoomError("room_stale_revision", "The room changed. Refresh and try again.")
        if status and room["status"] != status:
            raise RoomError("room_wrong_phase", "This action is not available right now.")
        return room, False

    def _bump(self, c, room_id, **values):
        if values.get("status") and values["status"] != "lobby":
            values["invite_code"] = None
        c.execute(
            update(learning_rooms)
            .where(learning_rooms.c.id == room_id)
            .values(
                revision=learning_rooms.c.revision + 1,
                updated_at=utc_now(),
                **values,
            )
        )

    def _reset_ready(self, c, room_id):
        c.execute(update(room_members).where(room_members.c.room_id == room_id).values(ready=False))

    @staticmethod
    def _stale_invitation(now):
        return or_(
            learning_rooms.c.status != "lobby",
            learning_rooms.c.invite_expires_at <= now,
            learning_rooms.c.expires_at <= now,
            learning_rooms.c.host_user_id.is_(None),
        )

    def create(self, request):
        room_id = uuid5(self.user_id, f"room:{request.command_id}")
        with self._locked(room_id) as c:
            existing = c.execute(
                select(learning_rooms.c.id).where(learning_rooms.c.id == room_id)
            ).first()
            if existing:
                self._member(c, room_id)
                if not self._remembered(c, room_id, "create", request):
                    raise RoomError("room_command_conflict", "This room key was already used.")
            else:
                profile = self._profile(c, request.language_profile_id)
                self._no_active_room(c)
                self._setup_rate(c)
                now = utc_now()
                invite_code = secrets.token_hex(32)
                c.execute(
                    insert(learning_rooms).values(
                        id=room_id,
                        host_user_id=self.user_id,
                        source_language_code=profile["source_language_code"].lower(),
                        target_language_code=profile["target_language_code"].lower(),
                        proficiency_level=profile["proficiency_level"],
                        status="lobby",
                        revision=0,
                        invite_hash=hashlib.sha256(invite_code.encode()).hexdigest(),
                        invite_code=invite_code,
                        invite_expires_at=now + INVITE_DURATION,
                        expires_at=now + LOBBY_DURATION,
                        ended_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self._add_member(c, room_id, profile["id"], 0)
                self._remember(c, room_id, "create", request)
            snapshot = self._snapshot(c, room_id)
        return RoomAccessResponse(room=snapshot, invite_code=snapshot.invite_code)

    def _add_member(self, c, room_id, profile_id, seat):
        c.execute(
            insert(room_members).values(
                id=uuid4(),
                room_id=room_id,
                user_id=self.user_id,
                language_profile_id=profile_id,
                seat=seat,
                ready=False,
                active=True,
                joined_at=utc_now(),
            )
        )

    def join(self, request):
        hashed = hashlib.sha256(request.invite_code.encode()).hexdigest()
        with self.engine.connect() as c:
            room_id = c.execute(
                select(learning_rooms.c.id).where(
                    learning_rooms.c.invite_hash == hashed,
                )
            ).scalar_one_or_none()
        if room_id is None:
            raise RoomError(
                "room_invite_invalid", "This invitation is invalid or unavailable.", 404
            )
        with self._locked(room_id) as c:
            room = self._room(c, room_id)
            if self._remembered(c, room_id, "join", request):
                return RoomAccessResponse(room=self._snapshot(c, room_id))
            if room["status"] != "lobby" or room["invite_expires_at"] <= utc_now():
                raise RoomError("room_invite_expired", "This invitation has expired.", 410)
            profile = self._profile(c, request.language_profile_id)
            if any(
                profile[field].lower() != room[field].lower()
                for field in (
                    "source_language_code",
                    "target_language_code",
                    "proficiency_level",
                )
            ):
                raise RoomError(
                    "room_language_mismatch", "Use the room's learning language and level.", 422
                )
            self._no_active_room(c, room_id)
            members = self._members(c, room_id)
            if not any(m["user_id"] == self.user_id for m in members):
                if len(members) >= 2:
                    raise RoomError("room_full", "This room already has two players.")
                self._setup_rate(c)
                self._add_member(c, room_id, profile["id"], 1)
                self._reset_ready(c, room_id)
                self._bump(c, room_id)
            self._remember(c, room_id, "join", request)
            return RoomAccessResponse(room=self._snapshot(c, room_id))

    def get(self, room_id):
        try:
            with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
                snapshot = self._snapshot(c, room_id)
                expired_invitation = c.execute(select(learning_rooms.c.id).where(
                    learning_rooms.c.id == room_id,
                    learning_rooms.c.invite_code.is_not(None),
                    self._stale_invitation(utc_now()),
                )).scalar_one_or_none()
            if expired_invitation:
                # Normal polling remains read-only. Expired credentials are
                # cleared under the same lock order as room commands.
                with self._locked(room_id) as c:
                    return self._snapshot(c, room_id)
            return snapshot
        except SQLAlchemyError as exc:
            raise RoomError(
                "room_storage_error", "The room could not be loaded. Try again.", 503
            ) from exc

    def active(self):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            room_id = c.execute(
                select(room_members.c.room_id)
                .join(
                    learning_rooms,
                    learning_rooms.c.id == room_members.c.room_id,
                )
                .where(
                    room_members.c.user_id == self.user_id,
                    room_members.c.active.is_(True),
                    learning_rooms.c.status.in_(LIVE),
                    learning_rooms.c.expires_at > utc_now(),
                )
            ).scalar_one_or_none()
        snapshot = self.get(room_id) if room_id else None
        return snapshot if snapshot and snapshot.status in LIVE else None

    def _photos(self, c, room_id):
        return [
            dict(row)
            for row in c.execute(
                select(room_photos)
                .where(
                    room_photos.c.room_id == room_id,
                )
                .order_by(room_photos.c.created_at, room_photos.c.id)
            ).mappings()
        ]

    def _photo(self, c, room_id, photo_id, own=False):
        row = (
            c.execute(
                select(room_photos).where(
                    room_photos.c.id == photo_id,
                    room_photos.c.room_id == room_id,
                )
            )
            .mappings()
            .first()
        )
        if row is None or (own and row["owner_user_id"] != self.user_id):
            raise RoomError("room_photo_not_found", "Photo not found.", 404)
        return dict(row)

    def _owned_asset(self, c, asset_id, owner_id=None):
        row = (
            c.execute(
                select(media_assets).where(
                    media_assets.c.id == asset_id,
                    media_assets.c.owner_user_id == (owner_id or self.user_id),
                    media_assets.c.media_type == "image",
                    media_assets.c.source.in_(["camera", "userUpload"]),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RoomError("room_photo_not_found", "Choose a photo you uploaded.", 404)
        return MediaAsset.model_validate(dict(row))

    def add_photo(self, room_id, request):
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, "addPhoto", request, "lobby")
            if not retry:
                self._owned_asset(c, request.media_asset_id)
                photos = self._photos(c, room_id)
                if len(photos) >= 4:
                    raise RoomError("room_photo_limit", "Use two to four photos in this room.")
                if any(p["media_asset_id"] == request.media_asset_id for p in photos):
                    raise RoomError("room_photo_duplicate", "This photo is already in the room.")
                additions = c.execute(
                    select(func.count())
                    .select_from(room_commands)
                    .where(
                        room_commands.c.room_id == room_id,
                        room_commands.c.kind == "addPhoto",
                    )
                ).scalar_one()
                if additions >= 8:
                    raise RoomError(
                        "room_photo_setup_limit", "Start a new room to try more photos.", 429
                    )
                now = utc_now()
                c.execute(
                    insert(room_photos).values(
                        id=uuid5(room_id, f"photo:{self.user_id}:{request.command_id}"),
                        room_id=room_id,
                        owner_user_id=self.user_id,
                        media_asset_id=request.media_asset_id,
                        status="queued",
                        moderation_passed=False,
                        content_hash=None,
                        analysis=None,
                        review=None,
                        pack=None,
                        processing_claim_id=None,
                        claim_expires_at=None,
                        analysis_attempts=0,
                        preparation_attempts=0,
                        error_code=None,
                        error_message=None,
                        retryable=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self._reset_ready(c, room_id)
                self._remember(c, room_id, "addPhoto", request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def remove_photo(self, room_id, photo_id, request):
        kind = f"removePhoto:{photo_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "lobby")
            if not retry:
                self._photo(c, room_id, photo_id, own=True)
                c.execute(delete(room_photos).where(room_photos.c.id == photo_id))
                self._reset_ready(c, room_id)
                self._remember(c, room_id, kind, request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def review_photo(self, room_id, photo_id, request):
        kind = f"reviewPhoto:{photo_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "lobby")
            if not retry:
                photo = self._photo(c, room_id, photo_id, own=True)
                if not photo["moderation_passed"] or not photo["analysis"]:
                    raise RoomError(
                        "room_photo_not_reviewable", "Wait for photo analysis before reviewing."
                    )
                if photo["preparation_attempts"] >= 3:
                    raise RoomError(
                        "room_photo_retry_limit", "Try a different photo after these attempts."
                    )
                keys = [o.key for o in request.review.objects]
                available = {o["key"] for o in photo["analysis"]["objects"]}
                if len(set(keys)) != len(keys) or not set(keys) <= available:
                    raise RoomError(
                        "room_photo_review_invalid",
                        "Review the objects detected in this photo.",
                        422,
                    )
                if any(
                    r.subject_object_key not in keys
                    or r.reference_object_key not in keys
                    or r.subject_object_key == r.reference_object_key
                    for r in request.review.relations
                ):
                    raise RoomError(
                        "room_photo_review_invalid",
                        "Relations must connect two selected objects.",
                        422,
                    )
                relations = request.review.relations
                if len({r.key for r in relations}) != len(relations) or len(
                    {(r.subject_object_key, r.relation, r.reference_object_key) for r in relations}
                ) != len(relations):
                    raise RoomError(
                        "room_photo_review_invalid", "Use each relationship only once.", 422
                    )
                c.execute(
                    update(room_photos)
                    .where(room_photos.c.id == photo_id)
                    .values(
                        status="preparing",
                        review=request.review.model_dump(mode="json", by_alias=True),
                        pack=None,
                        processing_claim_id=None,
                        claim_expires_at=None,
                        error_code=None,
                        error_message=None,
                        retryable=False,
                        updated_at=utc_now(),
                    )
                )
                self._reset_ready(c, room_id)
                self._remember(c, room_id, kind, request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def retry_photo(self, room_id, photo_id, request):
        kind = f"retryPhoto:{photo_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "lobby")
            if not retry:
                photo = self._photo(c, room_id, photo_id, own=True)
                expired = photo["claim_expires_at"] and photo["claim_expires_at"] <= utc_now()
                if not ((photo["status"] == "failed" and photo["retryable"]) or expired):
                    raise RoomError(
                        "room_photo_not_retryable", "This photo cannot retry right now."
                    )
                if (photo["review"] and photo["preparation_attempts"] >= 3) or (
                    not photo["review"] and photo["analysis_attempts"] >= 3
                ):
                    raise RoomError(
                        "room_photo_retry_limit", "Try a different photo after these attempts."
                    )
                status = "preparing" if photo["moderation_passed"] and photo["review"] else "queued"
                c.execute(
                    update(room_photos)
                    .where(room_photos.c.id == photo_id)
                    .values(
                        status=status,
                        processing_claim_id=None,
                        claim_expires_at=None,
                        error_code=None,
                        error_message=None,
                        retryable=False,
                        updated_at=utc_now(),
                    )
                )
                self._reset_ready(c, room_id)
                self._remember(c, room_id, kind, request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def ready(self, room_id, request):
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, "ready", request, "lobby")
            if not retry:
                photos = self._photos(c, room_id)
                if request.ready and (
                    not 2 <= len(photos) <= 4 or any(p["status"] != "ready" for p in photos)
                ):
                    raise RoomError(
                        "room_photos_not_ready", "Review two to four photos before getting ready."
                    )
                c.execute(
                    update(room_members)
                    .where(
                        room_members.c.room_id == room_id,
                        room_members.c.user_id == self.user_id,
                    )
                    .values(ready=request.ready)
                )
                self._remember(c, room_id, "ready", request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def start(self, room_id, request):
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, "start", request, "lobby")
            if not retry:
                members = self._members(c, room_id)
                photos = self._photos(c, room_id)
                if len(members) != 2 or not all(m["ready"] for m in members):
                    raise RoomError(
                        "room_players_not_ready", "Both players need to get ready first."
                    )
                if not 2 <= len(photos) <= 4 or any(
                    p["status"] != "ready" or not p["pack"] for p in photos
                ):
                    raise RoomError(
                        "room_photos_not_ready", "Review two to four photos before starting."
                    )
                for member in sorted(members, key=lambda m: str(m["user_id"])):
                    if self.spend_sauce:
                        self.spend_sauce(c, member["user_id"], f"room:{room_id}:start")
                for index, photo in enumerate(photos):
                    targets = photo["pack"].get("targets", [])
                    if not targets:
                        raise RoomError("room_photo_no_clues", "A photo needs a clear guided clue.")
                    target = secrets.choice(targets)
                    turn_id = uuid5(room_id, f"turn:{index}")
                    sender, guesser = members[index % 2], members[1 - index % 2]
                    now = utc_now()
                    c.execute(
                        insert(room_turns).values(
                            id=turn_id,
                            room_id=room_id,
                            photo_id=photo["id"],
                            turn_index=index,
                            sender_user_id=sender["user_id"],
                            guesser_user_id=guesser["user_id"],
                            phase="compose",
                            target_object_key=target["objectKey"],
                            clue_option_id=None,
                            clue=None,
                            guessed_object_keys=[],
                            is_correct=None,
                            created_at=now,
                            resolved_at=None,
                        )
                    )
                    for member in members:
                        c.execute(
                            insert(room_contributions).values(
                                id=uuid5(turn_id, str(member["user_id"])),
                                room_id=room_id,
                                turn_id=turn_id,
                                user_id=member["user_id"],
                                clue_sent=False,
                                guess_count=0,
                                correct_guess=False,
                                acknowledged=False,
                                basil_earned=0,
                                xp_earned=0,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                self._remember(c, room_id, "start", request)
                self._bump(
                    c,
                    room_id,
                    status="playing",
                    expires_at=utc_now() + PLAY_DURATION,
                    invite_expires_at=utc_now(),
                )
            return self._snapshot(c, room_id)

    def _current_turn(self, c, room_id):
        row = (
            c.execute(
                select(room_turns)
                .where(
                    room_turns.c.room_id == room_id,
                    room_turns.c.phase != "closed",
                )
                .order_by(room_turns.c.turn_index)
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _turn(self, c, room_id, turn_id, phase, role):
        turn = self._current_turn(c, room_id)
        if turn is None or turn["id"] != turn_id:
            raise RoomError("room_turn_changed", "The round changed. Refresh and try again.")
        if turn["phase"] != phase or turn[f"{role}_user_id"] != self.user_id:
            raise RoomError("room_wrong_role", "Wait for your turn.")
        return turn

    def _contribution(self, c, turn_id, **values):
        c.execute(
            update(room_contributions)
            .where(
                room_contributions.c.turn_id == turn_id,
                room_contributions.c.user_id == self.user_id,
            )
            .values(updated_at=utc_now(), **values)
        )

    def _basil(self, c, source_key):
        return int(self.reward_basil(c, self.user_id, source_key) or 0) if self.reward_basil else 0

    def clue(self, room_id, turn_id, request):
        kind = f"clue:{turn_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "playing")
            if not retry:
                turn = self._turn(c, room_id, turn_id, "compose", "sender")
                photo = self._photo(c, room_id, turn["photo_id"])
                target = next(
                    t
                    for t in photo["pack"]["targets"]
                    if t["objectKey"] == turn["target_object_key"]
                )
                option = next(
                    (o for o in target["clueOptions"] if o["id"] == request.clue_option_id), None
                )
                if option is None:
                    raise RoomError("room_clue_invalid", "Choose one of the offered clues.", 422)
                c.execute(
                    update(room_turns)
                    .where(room_turns.c.id == turn_id)
                    .values(
                        phase="guess",
                        clue_option_id=option["id"],
                        clue=option["text"],
                    )
                )
                earned = self._basil(c, f"room:{room_id}:turn:{turn_id}:clue")
                self._contribution(c, turn_id, clue_sent=True, basil_earned=earned)
                self._remember(c, room_id, kind, request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def guess(self, room_id, turn_id, request):
        kind = f"guess:{turn_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "playing")
            if not retry:
                turn = self._turn(c, room_id, turn_id, "guess", "guesser")
                photo = self._photo(c, room_id, turn["photo_id"])
                if request.object_key not in {o["key"] for o in photo["pack"]["objects"]}:
                    raise RoomError("room_guess_invalid", "Choose an object from this photo.", 422)
                guesses = turn["guessed_object_keys"]
                if request.object_key in guesses:
                    raise RoomError("room_guess_repeated", "Try another object.", 422)
                guesses = [*guesses, request.object_key]
                correct = request.object_key == turn["target_object_key"]
                resolved = correct or len(guesses) >= 2
                c.execute(
                    update(room_turns)
                    .where(room_turns.c.id == turn_id)
                    .values(
                        guessed_object_keys=guesses,
                        phase="reveal" if resolved else "guess",
                        is_correct=correct if resolved else None,
                        resolved_at=utc_now() if resolved else None,
                    )
                )
                member = self._member(c, room_id)
                xp = (
                    award(
                        c,
                        user_id=self.user_id,
                        language_profile_id=member["language_profile_id"],
                        event_type="ispyCorrect",
                        idempotency_key=f"room:{room_id}:turn:{turn_id}:correct",
                    )
                    if correct
                    else 0
                )
                earned = (
                    self._basil(c, f"room:{room_id}:turn:{turn_id}:guess")
                    if len(guesses) == 1
                    else 0
                )
                self._contribution(
                    c,
                    turn_id,
                    guess_count=len(guesses),
                    correct_guess=correct,
                    basil_earned=room_contributions.c.basil_earned + earned,
                    xp_earned=room_contributions.c.xp_earned + xp,
                )
                self._remember(c, room_id, kind, request)
                self._bump(c, room_id)
            return self._snapshot(c, room_id)

    def acknowledge(self, room_id, turn_id, request):
        kind = f"ack:{turn_id}"
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, kind, request, "playing")
            if not retry:
                turn = self._current_turn(c, room_id)
                if turn is None or turn["id"] != turn_id or turn["phase"] != "reveal":
                    raise RoomError("room_wrong_phase", "Wait for the round's result.")
                self._contribution(c, turn_id, acknowledged=True)
                remaining = c.execute(
                    select(func.count())
                    .select_from(room_contributions)
                    .where(
                        room_contributions.c.turn_id == turn_id,
                        room_contributions.c.acknowledged.is_(False),
                    )
                ).scalar_one()
                if remaining == 0:
                    c.execute(
                        update(room_turns).where(room_turns.c.id == turn_id).values(phase="closed")
                    )
                    if self._current_turn(c, room_id) is None:
                        self._bump(c, room_id, status="completed", ended_at=utc_now())
                        c.execute(
                            update(room_members)
                            .where(room_members.c.room_id == room_id)
                            .values(active=False)
                        )
                    else:
                        self._bump(c, room_id)
                else:
                    self._bump(c, room_id)
                self._remember(c, room_id, kind, request)
            return self._snapshot(c, room_id)

    def leave(self, room_id, request):
        with self._locked(room_id) as c:
            _room, retry = self._check_command(c, room_id, "leave", request)
            if not retry:
                now = utc_now()
                self._bump(c, room_id, status="ended", ended_at=now, invite_expires_at=now)
                c.execute(
                    update(room_members)
                    .where(room_members.c.room_id == room_id)
                    .values(active=False)
                )
                self._remember(c, room_id, "leave", request)
            return self._snapshot(c, room_id)

    def claim_photo(self, room_id, photo_id):
        with self._locked(room_id) as c:
            room = self._room(c, room_id)
            self._member(c, room_id, active=True)
            photo = self._photo(c, room_id, photo_id, own=True)
            if _effective_status(room) != "lobby" or photo["status"] not in {"queued", "preparing"}:
                return None
            if photo["processing_claim_id"] and photo["claim_expires_at"] > utc_now():
                return None
            phase = "analysis" if photo["status"] == "queued" else "pack"
            asset = self._owned_asset(c, photo["media_asset_id"])
            claim_id = uuid4()
            c.execute(
                update(room_photos)
                .where(room_photos.c.id == photo_id)
                .values(
                    status="analyzing" if phase == "analysis" else "preparing",
                    processing_claim_id=claim_id,
                    claim_expires_at=utc_now() + PHOTO_LEASE,
                    analysis_attempts=room_photos.c.analysis_attempts
                    + (1 if phase == "analysis" else 0),
                    preparation_attempts=room_photos.c.preparation_attempts
                    + (1 if phase == "pack" else 0),
                    updated_at=utc_now(),
                )
            )
            self._bump(c, room_id)
            member = self._member(c, room_id)
            profile = {
                "id": member["language_profile_id"],
                "room_id": room_id,
                "source_language_code": room["source_language_code"],
                "target_language_code": room["target_language_code"],
                "proficiency_level": room["proficiency_level"],
            }
            return RoomPhotoJob(
                photo_id,
                room_id,
                self.user_id,
                claim_id,
                phase,
                asset,
                profile,
                photo["analysis"],
                photo["review"],
            )

    def finish_photo(self, job, result=None, error=None):
        with self._locked(job.room_id) as c:
            room = self._room(c, job.room_id)
            photo = (
                c.execute(select(room_photos).where(room_photos.c.id == job.photo_id))
                .mappings()
                .first()
            )
            if (
                photo is None
                or photo["processing_claim_id"] != job.claim_id
                or photo["claim_expires_at"] is None
                or photo["claim_expires_at"] <= utc_now()
                or _effective_status(room) != "lobby"
            ):
                return
            if not photo["owner_user_id"] or not photo["media_asset_id"]:
                return
            values = dict(processing_claim_id=None, claim_expires_at=None, updated_at=utc_now())
            if error:
                values.update(
                    status="failed",
                    error_code=error.code,
                    error_message=error.message[:300],
                    retryable=error.retryable,
                )
            elif job.phase == "analysis":
                if not result or result.get("moderationPassed") is not True:
                    values.update(
                        status="failed",
                        moderation_passed=False,
                        error_code="room_photo_unsafe",
                        error_message="This photo could not be safely shared.",
                        retryable=False,
                    )
                elif (
                    result.get("contentHash")
                    and c.execute(
                        select(room_photos.c.id).where(
                            room_photos.c.room_id == job.room_id,
                            room_photos.c.id != job.photo_id,
                            room_photos.c.content_hash == result["contentHash"],
                        )
                    ).first()
                ):
                    values.update(
                        status="failed",
                        moderation_passed=False,
                        error_code="room_photo_duplicate",
                        retryable=False,
                        error_message="This photo is already here. Choose a different photo.",
                    )
                else:
                    values.update(
                        status="awaitingReview",
                        moderation_passed=True,
                        analysis=result,
                        content_hash=result.get("contentHash"),
                        error_code=None,
                        error_message=None,
                        retryable=False,
                    )
            else:
                if not result or not result.get("targets") or not result.get("objects"):
                    values.update(
                        status="failed",
                        error_code="room_photo_no_clues",
                        error_message="Review this photo's colours and positions for a clear clue.",
                        retryable=False,
                    )
                else:
                    values.update(
                        status="ready",
                        pack=result,
                        error_code=None,
                        error_message=None,
                        retryable=False,
                    )
            c.execute(update(room_photos).where(room_photos.c.id == job.photo_id).values(**values))
            self._reset_ready(c, job.room_id)
            self._bump(c, job.room_id)

    def authorized_photo_asset(self, user_id, room_id, photo_id):
        if user_id != self.user_id:
            raise RoomError("room_not_found", "Room not found.", 404)
        with self.engine.connect() as c:
            self._member(c, room_id, active=True)
            room = self._room(c, room_id)
            if _effective_status(room) not in LIVE:
                raise RoomError("room_not_active", "This room has ended.", 404)
            photo = self._photo(c, room_id, photo_id)
            if room["status"] == "playing":
                turn = self._current_turn(c, room_id)
                if turn is None or turn["photo_id"] != photo_id:
                    raise RoomError("room_photo_not_found", "Photo not found.", 404)
            if photo["owner_user_id"] != self.user_id and not photo["moderation_passed"]:
                raise RoomError("room_photo_not_found", "Photo not found.", 404)
            return self._owned_asset(c, photo["media_asset_id"], photo["owner_user_id"])

    def _snapshot(self, c, room_id):
        self._member(c, room_id)
        room = self._room(c, room_id)
        status = _effective_status(room)
        members = self._members(c, room_id)
        photos = self._photos(c, room_id)
        turn = self._current_turn(c, room_id) if status == "playing" else None
        contributions = [
            dict(row)
            for row in c.execute(
                select(room_contributions).where(
                    room_contributions.c.room_id == room_id,
                )
            ).mappings()
        ]
        public_members = [
            RoomMemberPublic(
                user_id=m["user_id"],
                display_name=m["display_name"],
                seat=m["seat"],
                ready=m["ready"],
                acknowledged=any(
                    x["acknowledged"]
                    for x in contributions
                    if turn and x["turn_id"] == turn["id"] and x["user_id"] == m["user_id"]
                ),
            )
            for m in members
        ]
        public_photos = []
        for photo in photos:
            if status not in LIVE or (turn and photo["id"] != turn["photo_id"]):
                continue
            owner = photo["owner_user_id"] == self.user_id
            accessible = owner or photo["moderation_passed"]
            stalled = (
                photo["processing_claim_id"]
                and photo["claim_expires_at"]
                and photo["claim_expires_at"] <= utc_now()
            )
            public_photos.append(
                RoomPhotoPublic(
                    id=photo["id"],
                    owner_user_id=photo["owner_user_id"],
                    media_asset_id=photo["media_asset_id"] if accessible else None,
                    status="failed" if stalled else photo["status"],
                    image_url=_image_url(room_id, photo["id"])
                    if accessible and photo["media_asset_id"]
                    else None,
                    review=(photo["review"] or photo["analysis"])
                    if owner and status == "lobby"
                    else None,
                    error_code="room_photo_timeout" if stalled else photo["error_code"],
                    error_message="Photo preparation stopped. Try again."
                    if stalled
                    else photo["error_message"],
                    retryable=bool(stalled) or photo["retryable"],
                    processing=bool(photo["processing_claim_id"]) and not bool(stalled),
                )
            )
        public_turn = None
        if turn:
            photo = next(p for p in photos if p["id"] == turn["photo_id"])
            sender = turn["sender_user_id"] == self.user_id
            target = next(
                t for t in photo["pack"]["targets"] if t["objectKey"] == turn["target_object_key"]
            )
            public_turn = RoomTurnPublic(
                id=turn["id"],
                index=turn["turn_index"],
                role="sender" if sender else "guesser",
                phase=turn["phase"],
                photo_id=photo["id"],
                image_url=_image_url(room_id, photo["id"]),
                objects=photo["pack"]["objects"],
                clue=turn["clue"],
                target_object_key=turn["target_object_key"]
                if sender or turn["phase"] == "reveal"
                else None,
                clue_options=target["clueOptions"]
                if sender and turn["phase"] == "compose"
                else None,
                guess_count=len(turn["guessed_object_keys"]),
                guessed_object_keys=turn["guessed_object_keys"],
                result={
                    "isCorrect": turn["is_correct"],
                    "targetObjectKey": turn["target_object_key"],
                    "message": "You found it together!"
                    if turn["is_correct"]
                    else "Here's the object the clue described.",
                }
                if turn["phase"] == "reveal"
                else None,
            )
        public_contributions = [
            RoomContributionPublic(
                user_id=m["user_id"],
                clues_sent=sum(
                    int(x["clue_sent"]) for x in contributions if x["user_id"] == m["user_id"]
                ),
                guesses_made=sum(
                    x["guess_count"] for x in contributions if x["user_id"] == m["user_id"]
                ),
                correct_guesses=sum(
                    int(x["correct_guess"]) for x in contributions if x["user_id"] == m["user_id"]
                ),
                basil_earned=sum(
                    x["basil_earned"] for x in contributions if x["user_id"] == m["user_id"]
                ),
                xp_earned=sum(
                    x["xp_earned"] for x in contributions if x["user_id"] == m["user_id"]
                ),
            )
            for m in members
        ]
        success = c.execute(
            select(func.count())
            .select_from(room_turns)
            .where(
                room_turns.c.room_id == room_id,
                room_turns.c.is_correct.is_(True),
            )
        ).scalar_one()
        return RoomSnapshot(
            id=room_id,
            status=status,
            revision=room["revision"],
            expires_at=room["expires_at"],
            me_id=self.user_id,
            host_user_id=room["host_user_id"],
            source_language_code=room["source_language_code"],
            target_language_code=room["target_language_code"],
            proficiency_level=room["proficiency_level"],
            members=public_members,
            photos=public_photos,
            current_turn=public_turn,
            successful_rounds=success,
            round_count=len(photos),
            contributions=public_contributions,
            invite_code=room["invite_code"]
            if (
                self.user_id == room["host_user_id"]
                and status == "lobby"
                and room["invite_expires_at"] > utc_now()
            )
            else None,
        )
