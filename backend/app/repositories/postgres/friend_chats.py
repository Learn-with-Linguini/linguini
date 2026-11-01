"""Persistent private I-Spy chats with serialized, replay-safe commands."""

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
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    and_,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.room_errors import RoomError
from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.friend_chats import (
    ChatAccess,
    ChatClueOption,
    ChatMessage,
    ChatObject,
    ChatPerson,
    ChatRound,
    ChatSnapshot,
    InvitePreview,
)
from app.schemas.media import MediaAsset
from app.services.room_languages import room_profile_supported

metadata = MetaData()


def _time(name, nullable=False):
    return Column(name, DateTime(timezone=True), nullable=nullable)


chats = Table(
    "friend_chats",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("creator_user_id", Uuid, nullable=False),
    Column("partner_user_id", Uuid),
    Column("creator_profile", JSONB, nullable=False),
    Column("partner_profile", JSONB(none_as_null=True)),
    Column("target_language_code", String(35), nullable=False),
    Column("status", String(12), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("invite_hash", String(64), nullable=False),
    Column("invite_status", String(12), nullable=False),
    _time("invite_expires_at"),
    _time("created_at"),
    _time("updated_at"),
    schema="public",
)
rounds = Table(
    "friend_chat_rounds",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("chat_id", Uuid, nullable=False),
    Column("sender_user_id", Uuid, nullable=False),
    Column("media_asset_id", Uuid),
    Column("status", String(24), nullable=False),
    Column("photo_status", String(12), nullable=False),
    Column("content", JSONB),
    Column("target", JSONB),
    Column("clue_options", JSONB, nullable=False),
    Column("claim_id", Uuid),
    _time("claim_expires_at", True),
    Column("analysis_attempts", Integer, nullable=False),
    Column("retryable", Boolean, nullable=False),
    Column("error", String(300)),
    _time("created_at"),
    _time("completed_at", True),
    schema="public",
)
messages = Table(
    "friend_chat_messages",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("chat_id", Uuid, nullable=False),
    Column("round_id", Uuid),
    Column("sender_user_id", Uuid),
    Column("type", String(24), nullable=False),
    Column("text", Text),
    Column("x", Float),
    Column("y", Float),
    Column("is_correct", Integer),
    _time("created_at"),
    schema="public",
)
commands = Table(
    "friend_chat_commands",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("chat_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("command_id", Uuid, nullable=False),
    Column("kind", String(100), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("result", JSONB),
    _time("created_at"),
    schema="public",
)
blocks = Table(
    "user_blocks",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("blocked_user_id", Uuid, nullable=False),
    _time("created_at"),
    schema="public",
)
reports = Table(
    "friend_chat_reports",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("chat_id", Uuid, nullable=False),
    Column("reporter_user_id", Uuid, nullable=False),
    Column("reported_user_id", Uuid, nullable=False),
    Column("reason", String(500), nullable=False),
    _time("created_at"),
    schema="public",
)
assistance = Table(
    "friend_chat_assistance",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("round_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    _time("created_at"),
    schema="public",
)

TERMINAL = {"completed", "cancelled"}
INVITE_DURATION = timedelta(days=7)
PHOTO_LEASE = timedelta(minutes=8)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _fingerprint(kind, request):
    body = request.model_dump(mode="json", by_alias=True)
    return _hash(json.dumps({"kind": kind, "body": body}, sort_keys=True, separators=(",", ":")))


def _public_clue_option(option):
    """Keep private grounding metadata out of the strict public option contract."""
    return ChatClueOption(
        id=option["id"],
        text=option["text"],
        translation=option["translation"],
        concept=option["concept"],
        cheat_sheet=option.get("cheatSheet"),
    )


@dataclass(frozen=True)
class ChatPhotoJob:
    chat_id: UUID
    round_id: UUID
    owner_id: UUID
    claim_id: UUID
    asset: MediaAsset
    profile: dict


class PostgresFriendChatRepository:
    def __init__(self, engine, user_id):
        self.engine, self.user_id = engine, user_id

    def _row(self, c, chat_id):
        row = c.execute(select(chats).where(chats.c.id == chat_id)).mappings().first()
        if row is None or self.user_id not in (row["creator_user_id"], row["partner_user_id"]):
            raise RoomError("chat_not_found", "I-Spy chat not found.", 404)
        return dict(row)

    @contextmanager
    def _locked(self, chat_id=None, *, extra_ids=()):
        """Use the same user-before-resource lock order as account deletion."""
        try:
            with self.engine.begin() as c:
                ids = {self.user_id, *extra_ids}
                if chat_id:
                    chat = c.execute(select(chats).where(chats.c.id == chat_id)).mappings().first()
                    if chat:
                        ids.update({chat["creator_user_id"], chat["partner_user_id"]} - {None})
                locked = set(
                    c.execute(
                        select(users.c.id)
                        .where(users.c.id.in_(ids))
                        .order_by(users.c.id)
                        .with_for_update()
                    ).scalars()
                )
                if self.user_id not in locked:
                    raise RoomError("chat_unauthenticated", "Sign in to play with a friend.", 401)
                if chat_id:
                    c.execute(
                        select(chats.c.id).where(chats.c.id == chat_id).with_for_update()
                    ).all()
                yield c
        except SQLAlchemyError as error:
            raise RoomError(
                "chat_storage_error", "Your I-Spy chat could not be saved. Try again.", 503
            ) from error

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
            raise RoomError("chat_profile_invalid", "Choose your active learning language.", 422)
        if not room_profile_supported(row, check_level=False):
            raise RoomError(
                "chat_language_unsupported", "I-Spy is not available for this language yet.", 422
            )
        return {
            "id": str(row["id"]),
            "source_language_code": row["source_language_code"],
            "target_language_code": row["target_language_code"],
            "proficiency_level": row["proficiency_level"],
        }

    def _blocked(self, c, first, second):
        return bool(
            second
            and c.execute(
                select(blocks.c.id).where(
                    or_(
                        and_(blocks.c.user_id == first, blocks.c.blocked_user_id == second),
                        and_(blocks.c.user_id == second, blocks.c.blocked_user_id == first),
                    )
                )
            ).first()
        )

    def _existing_command(self, c, chat_id, kind, request):
        row = (
            c.execute(
                select(commands).where(
                    commands.c.chat_id == chat_id,
                    commands.c.user_id == self.user_id,
                    commands.c.command_id == request.command_id,
                )
            )
            .mappings()
            .first()
        )
        if row and row["fingerprint"] != _fingerprint(kind, request):
            raise RoomError(
                "chat_command_conflict", "This action was already used. Refresh and try again."
            )
        return row

    def _remember(self, c, chat_id, kind, request, result=None):
        c.execute(
            insert(commands).values(
                id=uuid4(),
                chat_id=chat_id,
                user_id=self.user_id,
                command_id=request.command_id,
                kind=kind,
                fingerprint=_fingerprint(kind, request),
                result=result,
                created_at=utc_now(),
            )
        )

    def _command(self, c, chat_id, kind, request, *, active=True):
        chat = self._row(c, chat_id)
        prior = self._existing_command(c, chat_id, kind, request)
        if prior:
            return chat, prior
        if active and chat["status"] not in {"waiting", "active"}:
            raise RoomError("chat_closed", "This I-Spy chat has ended.", 409)
        if request.expected_revision != chat["revision"]:
            raise RoomError("chat_stale_revision", "The chat changed. Refresh and try again.", 409)
        return chat, None

    def _bump(self, c, chat_id, **values):
        c.execute(
            update(chats)
            .where(chats.c.id == chat_id)
            .values(
                revision=chats.c.revision + 1,
                updated_at=utc_now(),
                **values,
            )
        )

    def _message(self, c, chat_id, round_id, kind, *, text=None, actor=None, **values):
        c.execute(
            insert(messages).values(
                id=uuid4(),
                chat_id=chat_id,
                round_id=round_id,
                type=kind,
                sender_user_id=actor,
                text=text,
                created_at=utc_now(),
                **values,
            )
        )

    def create(self, request):
        chat_id = uuid5(self.user_id, f"friend-chat:{request.command_id}")
        with self._locked(chat_id) as c:
            existing = c.execute(select(chats.c.id).where(chats.c.id == chat_id)).first()
            if existing:
                self._row(c, chat_id)
                if not self._existing_command(c, chat_id, "create", request):
                    raise RoomError("chat_command_conflict", "This action was already used.")
                return ChatAccess(chat=self._snapshot(c, chat_id), invite_token="")
            recent = c.execute(
                select(func.count())
                .select_from(chats)
                .where(
                    chats.c.creator_user_id == self.user_id,
                    chats.c.created_at > utc_now() - timedelta(hours=1),
                )
            ).scalar_one()
            if recent >= 10:
                raise RoomError(
                    "chat_rate_limited", "You've made several chats. Try again later.", 429
                )
            profile = self._profile(c, request.language_profile_id)
            token, now = secrets.token_urlsafe(32), utc_now()
            c.execute(
                insert(chats).values(
                    id=chat_id,
                    creator_user_id=self.user_id,
                    partner_user_id=None,
                    creator_profile=profile,
                    partner_profile=None,
                    target_language_code=profile["target_language_code"].lower(),
                    status="waiting",
                    revision=0,
                    invite_hash=_hash(token),
                    invite_status="open",
                    invite_expires_at=now + INVITE_DURATION,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._remember(c, chat_id, "create", request)
            return ChatAccess(chat=self._snapshot(c, chat_id), invite_token=token)

    def preview(self, token):
        with self.engine.connect() as c:
            row = (
                c.execute(select(chats).where(chats.c.invite_hash == _hash(token)))
                .mappings()
                .first()
            )
            if row is None:
                raise RoomError("chat_invite_invalid", "This I-Spy invitation is invalid.", 404)
            if row["partner_user_id"]:
                return InvitePreview(status="full")
            if row["invite_status"] != "open" or row["status"] != "waiting":
                return InvitePreview(status="revoked")
            if row["invite_expires_at"] <= utc_now():
                return InvitePreview(status="expired")
            if self._blocked(c, self.user_id, row["creator_user_id"]):
                return InvitePreview(status="revoked")
            return InvitePreview(
                status="open",
                creator=self._person(c, row["creator_user_id"]),
                target_language_code=row["target_language_code"],
            )

    def join(self, request):
        with self.engine.connect() as c:
            chat_id = c.execute(
                select(chats.c.id).where(
                    chats.c.invite_hash == _hash(request.invite_token),
                )
            ).scalar_one_or_none()
        if chat_id is None:
            raise RoomError("chat_invite_invalid", "This I-Spy invitation is invalid.", 404)
        with self._locked(chat_id) as c:
            chat = dict(c.execute(select(chats).where(chats.c.id == chat_id)).mappings().one())
            if self.user_id in (chat["creator_user_id"], chat["partner_user_id"]):
                self._row(c, chat_id)
                prior = self._existing_command(c, chat_id, "join", request)
                if prior or chat["status"] in {"waiting", "active"}:
                    return self._snapshot(c, chat_id)
            if chat["partner_user_id"]:
                raise RoomError("chat_full", "This I-Spy chat already has two players.", 409)
            if chat["status"] != "waiting" or chat["invite_status"] != "open":
                raise RoomError(
                    "chat_invite_revoked", "This I-Spy invitation is no longer available.", 410
                )
            if chat["invite_expires_at"] <= utc_now():
                raise RoomError("chat_invite_expired", "This I-Spy invitation has expired.", 410)
            if self._blocked(c, self.user_id, chat["creator_user_id"]):
                raise RoomError(
                    "chat_invite_revoked", "This I-Spy invitation is no longer available.", 410
                )
            profile = self._profile(c, request.language_profile_id)
            if profile["target_language_code"].lower() != chat["target_language_code"]:
                raise RoomError(
                    "chat_language_mismatch",
                    "Switch to this chat's learning language or create a profile to join.",
                    422,
                )
            self._bump(
                c,
                chat_id,
                partner_user_id=self.user_id,
                partner_profile=profile,
                status="active",
                invite_status="accepted",
            )
            self._message(
                c,
                chat_id,
                None,
                "system",
                text=f"{self._person(c, self.user_id).display_name} joined your I-Spy chat.",
                actor=self.user_id,
            )
            self._remember(c, chat_id, "join", request)
            return self._snapshot(c, chat_id)

    def get(self, chat_id):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            return self._snapshot(c, chat_id)

    def list(self):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            ids = (
                c.execute(
                    select(chats.c.id)
                    .where(
                        or_(
                            chats.c.creator_user_id == self.user_id,
                            chats.c.partner_user_id == self.user_id,
                        )
                    )
                    .order_by(chats.c.updated_at.desc(), chats.c.id)
                )
                .scalars()
                .all()
            )
            return [self._snapshot(c, chat_id) for chat_id in ids]

    def rotate_invite(self, chat_id, request):
        with self._locked(chat_id) as c:
            chat, prior = self._command(c, chat_id, "invite", request)
            if chat["creator_user_id"] != self.user_id or chat["partner_user_id"]:
                raise RoomError("chat_invite_closed", "This chat's invitation is closed.", 409)
            if not prior:
                token = secrets.token_urlsafe(32)
                self._bump(
                    c,
                    chat_id,
                    invite_hash=_hash(token),
                    invite_status="open",
                    invite_expires_at=utc_now() + INVITE_DURATION,
                )
                self._remember(c, chat_id, "invite", request)
            return ChatAccess(chat=self._snapshot(c, chat_id), invite_token="" if prior else token)

    def revoke_invite(self, chat_id, request):
        with self._locked(chat_id) as c:
            chat, prior = self._command(c, chat_id, "revokeInvite", request)
            if chat["creator_user_id"] != self.user_id or chat["partner_user_id"]:
                raise RoomError("chat_invite_closed", "This chat's invitation is closed.", 409)
            if not prior:
                self._bump(c, chat_id, invite_status="revoked")
                self._remember(c, chat_id, "revokeInvite", request)
            return self._snapshot(c, chat_id)

    def replay(self, chat_id, kind, request):
        with self.engine.connect() as c:
            self._row(c, chat_id)
            prior = self._existing_command(c, chat_id, kind, request)
            if prior:
                return True, prior["result"] or self._snapshot(c, chat_id)
            return False, None

    def close(self, chat_id, request, *, block=False):
        kind = "block" if block else "leave"
        with self._locked(chat_id) as c:
            chat, prior = self._command(c, chat_id, kind, request, active=False)
            if not prior:
                other = (
                    chat["partner_user_id"]
                    if self.user_id == chat["creator_user_id"]
                    else chat["creator_user_id"]
                )
                ids = [chat_id]
                if block and other:
                    c.execute(
                        pg_insert(blocks)
                        .values(
                            id=uuid4(),
                            user_id=self.user_id,
                            blocked_user_id=other,
                            created_at=utc_now(),
                        )
                        .on_conflict_do_nothing(
                            index_elements=[blocks.c.user_id, blocks.c.blocked_user_id]
                        )
                    )
                    ids = (
                        c.execute(
                            select(chats.c.id)
                            .where(
                                or_(
                                    and_(
                                        chats.c.creator_user_id == self.user_id,
                                        chats.c.partner_user_id == other,
                                    ),
                                    and_(
                                        chats.c.creator_user_id == other,
                                        chats.c.partner_user_id == self.user_id,
                                    ),
                                )
                            )
                            .order_by(chats.c.id)
                            .with_for_update()
                        )
                        .scalars()
                        .all()
                    )
                for target_id in ids:
                    self._bump(
                        c, target_id, status="blocked" if block else "left", invite_status="revoked"
                    )
                    c.execute(
                        update(rounds)
                        .where(rounds.c.chat_id == target_id, rounds.c.status.not_in(TERMINAL))
                        .values(
                            status="cancelled",
                            completed_at=utc_now(),
                            claim_id=None,
                            claim_expires_at=None,
                            target=None,
                            clue_options=[],
                        )
                    )
                self._remember(c, chat_id, kind, request)
            return self._snapshot(c, chat_id)

    def report(self, chat_id, request):
        with self._locked(chat_id) as c:
            chat, prior = self._command(c, chat_id, "report", request, active=False)
            other = (
                chat["partner_user_id"]
                if self.user_id == chat["creator_user_id"]
                else chat["creator_user_id"]
            )
            if not other:
                raise RoomError("chat_no_partner", "No friend has joined this chat yet.", 422)
            if not prior:
                c.execute(
                    insert(reports).values(
                        id=uuid4(),
                        chat_id=chat_id,
                        reporter_user_id=self.user_id,
                        reported_user_id=other,
                        reason=request.reason,
                        created_at=utc_now(),
                    )
                )
                self._remember(c, chat_id, "report", request)
            return self._snapshot(c, chat_id)

    def start_round(self, chat_id, request):
        with self._locked(chat_id) as c:
            chat, prior = self._command(c, chat_id, "startRound", request)
            if not prior:
                if chat["status"] != "active":
                    raise RoomError("chat_waiting", "Wait for your friend to join.", 409)
                if c.execute(
                    select(rounds.c.id).where(
                        rounds.c.chat_id == chat_id, rounds.c.status.not_in(TERMINAL)
                    )
                ).first():
                    raise RoomError("chat_round_active", "A new I-Spy has already started.", 409)
                self._asset(c, request.media_asset_id, self.user_id)
                recent = c.execute(
                    select(func.count())
                    .select_from(rounds)
                    .where(
                        rounds.c.sender_user_id == self.user_id,
                        rounds.c.created_at > utc_now() - timedelta(hours=1),
                    )
                ).scalar_one()
                if recent >= 20:
                    raise RoomError(
                        "chat_rate_limited", "You've started several rounds. Try again later.", 429
                    )
                c.execute(
                    insert(rounds).values(
                        id=uuid5(chat_id, f"round:{self.user_id}:{request.command_id}"),
                        chat_id=chat_id,
                        sender_user_id=self.user_id,
                        media_asset_id=request.media_asset_id,
                        status="selectingTarget",
                        photo_status="analyzing",
                        content=None,
                        target=None,
                        clue_options=[],
                        claim_id=None,
                        claim_expires_at=None,
                        analysis_attempts=0,
                        retryable=False,
                        error=None,
                        created_at=utc_now(),
                        completed_at=None,
                    )
                )
                self._remember(c, chat_id, "startRound", request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def _asset(self, c, asset_id, owner_id):
        row = (
            c.execute(
                select(media_assets).where(
                    media_assets.c.id == asset_id,
                    media_assets.c.owner_user_id == owner_id,
                    media_assets.c.media_type == "image",
                    media_assets.c.source.in_(["camera", "userUpload"]),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RoomError("chat_photo_invalid", "Choose one of your uploaded photos.", 422)
        return MediaAsset.model_validate(dict(row))

    def _round(self, c, chat_id, round_id, *, sender=None, phases=None):
        row = (
            c.execute(select(rounds).where(rounds.c.id == round_id, rounds.c.chat_id == chat_id))
            .mappings()
            .first()
        )
        if row is None:
            raise RoomError("chat_round_not_found", "I-Spy round not found.", 404)
        if sender is not None and (row["sender_user_id"] == self.user_id) != sender:
            raise RoomError("chat_wrong_role", "Wait for your friend's turn.", 403)
        if phases is not None and row["status"] not in phases:
            raise RoomError(
                "chat_wrong_phase", "This I-Spy round has changed. Refresh and try again.", 409
            )
        return dict(row)

    def context(self, chat_id, round_id, *, sender=None, phases=None):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            chat = self._row(c, chat_id)
            if chat["status"] != "active":
                raise RoomError("chat_closed", "This I-Spy chat has ended.", 409)
            item = self._round(c, chat_id, round_id, sender=sender, phases=phases)
            profile = dict(
                chat["creator_profile"]
                if self.user_id == chat["creator_user_id"]
                else chat["partner_profile"]
            )
            profile = self._enrich_profile(c, profile)
            previous = (
                c.execute(
                    select(messages.c.text)
                    .where(
                        messages.c.round_id == round_id,
                        messages.c.type.in_(["clue", "followUpClue"]),
                    )
                    .order_by(messages.c.created_at)
                )
                .scalars()
                .all()
            )
            return {"chat": chat, "round": item, "profile": profile, "previous_clues": previous}

    def _enrich_profile(self, c, profile):
        from app.repositories.postgres.practice import sessions
        from app.repositories.postgres.tasks import session_tasks

        content = c.execute(
            select(session_tasks.c.public_content)
            .join(sessions, sessions.c.id == session_tasks.c.session_id)
            .where(
                sessions.c.user_id == self.user_id,
                sessions.c.language_profile_id == UUID(profile["id"]),
                session_tasks.c.status == "completed",
            )
        ).scalars()
        completed = set()
        for item in content:
            if not isinstance(item, dict):
                continue
            mission = item.get("mission", {})
            if not isinstance(mission, dict):
                mission = {}
            code = mission.get("missionId") or mission.get("missionCode") or item.get("missionId")
            if code:
                completed.add(code)
        return {**profile, "completed_missions": sorted(completed)}

    def claim_photo(self, chat_id, round_id):
        with self._locked(chat_id) as c:
            chat = self._row(c, chat_id)
            item = self._round(c, chat_id, round_id, sender=True)
            if (
                chat["status"] != "active"
                or item["status"] in TERMINAL
                or item["photo_status"] != "analyzing"
            ):
                return None
            if item["claim_id"] and item["claim_expires_at"] > utc_now():
                return None
            if item["analysis_attempts"] >= 3:
                return None
            claim_id = uuid4()
            c.execute(
                update(rounds)
                .where(rounds.c.id == round_id)
                .values(
                    claim_id=claim_id,
                    claim_expires_at=utc_now() + PHOTO_LEASE,
                    analysis_attempts=rounds.c.analysis_attempts + 1,
                )
            )
            profile = (
                chat["creator_profile"]
                if self.user_id == chat["creator_user_id"]
                else chat["partner_profile"]
            )
            return ChatPhotoJob(
                chat_id,
                round_id,
                self.user_id,
                claim_id,
                self._asset(c, item["media_asset_id"], self.user_id),
                self._enrich_profile(c, dict(profile)),
            )

    def finish_photo(self, job, *, content=None, error=None, retryable=True):
        with self._locked(job.chat_id) as c:
            chat = self._row(c, job.chat_id)
            item = self._round(c, job.chat_id, job.round_id)
            if (
                chat["status"] != "active"
                or item["status"] in TERMINAL
                or item["claim_id"] != job.claim_id
                or item["claim_expires_at"] <= utc_now()
            ):
                return
            c.execute(
                update(rounds)
                .where(rounds.c.id == job.round_id)
                .values(
                    content=content,
                    photo_status="failed" if error else "ready",
                    error=error,
                    retryable=bool(error) and retryable,
                    claim_id=None,
                    claim_expires_at=None,
                )
            )
            self._bump(c, job.chat_id)

    def retry(self, chat_id, round_id, request):
        kind = f"retry:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            if not prior:
                item = self._round(c, chat_id, round_id, sender=True, phases={"selectingTarget"})
                stalled = item["claim_id"] and item["claim_expires_at"] <= utc_now()
                if (
                    item["analysis_attempts"] >= 3
                    or (item["photo_status"] != "failed" and not stalled)
                    or (item["photo_status"] == "failed" and not item["retryable"])
                ):
                    raise RoomError(
                        "chat_retry_unavailable",
                        "This photo cannot be retried. Choose another photo.",
                        409,
                    )
                c.execute(
                    update(rounds)
                    .where(rounds.c.id == round_id)
                    .values(
                        photo_status="analyzing",
                        claim_id=None,
                        claim_expires_at=None,
                        error=None,
                        retryable=False,
                    )
                )
                self._remember(c, chat_id, kind, request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def select_target(self, chat_id, round_id, request, target, options):
        kind = f"target:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            if not prior:
                item = self._round(
                    c, chat_id, round_id, sender=True, phases={"selectingTarget", "composingClue"}
                )
                if item["photo_status"] != "ready":
                    raise RoomError(
                        "chat_photo_not_ready", "Wait for the photo to finish analyzing.", 409
                    )
                content = dict(item["content"])
                objects = list(content.get("objects", []))
                if not any(obj["key"] == target["key"] for obj in objects):
                    objects.append(target)
                content["objects"] = objects
                c.execute(
                    update(rounds)
                    .where(rounds.c.id == round_id)
                    .values(
                        content=content,
                        target=target,
                        clue_options=options if request.confirm else [],
                        status="composingClue" if request.confirm else "selectingTarget",
                    )
                )
                self._remember(c, chat_id, kind, request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def send_clue(self, chat_id, round_id, request, text):
        kind = f"clue:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            if not prior:
                item = self._round(
                    c, chat_id, round_id, sender=True, phases={"composingClue", "awaitingFollowUp"}
                )
                if not item["target"]:
                    raise RoomError("chat_target_missing", "Confirm the hidden object first.", 409)
                follow_up = item["status"] == "awaitingFollowUp"
                self._message(
                    c,
                    chat_id,
                    round_id,
                    "followUpClue" if follow_up else "clue",
                    text=text,
                    actor=self.user_id,
                )
                c.execute(
                    update(rounds).where(rounds.c.id == round_id).values(status="awaitingGuess")
                )
                self._remember(c, chat_id, kind, request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def suggestion(self, chat_id, round_id, request, text):
        kind = f"suggest:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            self._round(
                c, chat_id, round_id, sender=True, phases={"composingClue", "awaitingFollowUp"}
            )
            if prior:
                return prior["result"]
            result = {"text": text}
            self._remember(c, chat_id, kind, request, result)
            return result

    def guess(self, chat_id, round_id, request):
        kind = f"guess:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            if not prior:
                item = self._round(c, chat_id, round_id, sender=False, phases={"awaitingGuess"})
                target = item["target"]
                region = target.get("region")
                width, height = target.get("width"), target.get("height")
                if region:
                    left, top = region["x"], region["y"]
                    width, height = region["width"], region["height"]
                elif width and height:
                    left, top = target["x"] - width / 2, target["y"] - height / 2
                else:
                    raise RoomError(
                        "chat_target_region_missing",
                        "The object needs a confirmed photo region. "
                        "Ask your friend to choose it again.",
                        409,
                    )
                correct = left <= request.x <= left + width and top <= request.y <= top + height
                self._message(
                    c,
                    chat_id,
                    round_id,
                    "guess",
                    actor=self.user_id,
                    x=request.x,
                    y=request.y,
                    is_correct=int(correct),
                )
                self._message(
                    c,
                    chat_id,
                    round_id,
                    "correctResult" if correct else "incorrectResult",
                    text=f"{self._person(c, self.user_id).display_name} found it!"
                    if correct
                    else "That wasn't the object.",
                    actor=self.user_id,
                    is_correct=int(correct),
                )
                c.execute(
                    update(rounds)
                    .where(rounds.c.id == round_id)
                    .values(
                        status="completed" if correct else "awaitingFollowUp",
                        completed_at=utc_now() if correct else None,
                    )
                )
                self._remember(c, chat_id, kind, request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def finish_round(self, chat_id, round_id, request, *, reveal=False):
        kind = f"{'reveal' if reveal else 'cancel'}:{round_id}"
        with self._locked(chat_id) as c:
            _chat, prior = self._command(c, chat_id, kind, request)
            if not prior:
                item = self._round(
                    c,
                    chat_id,
                    round_id,
                    sender=True,
                    phases={"awaitingGuess", "awaitingFollowUp"}
                    if reveal
                    else set(
                        ["selectingTarget", "composingClue", "awaitingGuess", "awaitingFollowUp"]
                    ),
                )
                if reveal:
                    target = item["target"]
                    self._message(
                        c,
                        chat_id,
                        round_id,
                        "reveal",
                        actor=self.user_id,
                        text=f"The object was {target['word']} — {target['translation']}.",
                    )
                c.execute(
                    update(rounds)
                    .where(rounds.c.id == round_id)
                    .values(
                        status="completed" if reveal else "cancelled",
                        completed_at=utc_now(),
                        claim_id=None,
                        claim_expires_at=None,
                        **({} if reveal else {"target": None, "clue_options": []}),
                    )
                )
                self._remember(c, chat_id, kind, request)
                self._bump(c, chat_id)
            return self._snapshot(c, chat_id)

    def record_help(self, chat_id, round_id):
        with self._locked(chat_id) as c:
            chat = self._row(c, chat_id)
            if chat["status"] != "active":
                raise RoomError("chat_closed", "This I-Spy chat has ended.", 409)
            self._round(
                c, chat_id, round_id, sender=False, phases={"awaitingGuess", "awaitingFollowUp"}
            )
            c.execute(
                insert(assistance).values(
                    id=uuid4(), round_id=round_id, user_id=self.user_id, created_at=utc_now()
                )
            )

    def image_asset(self, chat_id, round_id):
        with self.engine.connect() as c:
            chat = self._row(c, chat_id)
            if chat["status"] not in {"waiting", "active"}:
                raise RoomError("chat_photo_unavailable", "This photo is no longer shared.", 404)
            item = self._round(c, chat_id, round_id)
            if item["status"] == "cancelled" or (
                item["sender_user_id"] != self.user_id
                and (
                    item["photo_status"] != "ready"
                    or item["status"] in {"selectingTarget", "composingClue"}
                )
            ):
                raise RoomError("chat_photo_unavailable", "This photo is not shared yet.", 404)
            return self._asset(c, item["media_asset_id"], item["sender_user_id"])

    def _person(self, c, user_id):
        row = (
            c.execute(
                select(users.c.id, users.c.display_name, users.c.avatar).where(
                    users.c.id == user_id
                )
            )
            .mappings()
            .one()
        )
        return ChatPerson(**dict(row))

    def _snapshot(self, c, chat_id):
        chat = self._row(c, chat_id)
        creator = chat["creator_user_id"] == self.user_id
        other_id = chat["partner_user_id"] if creator else chat["creator_user_id"]
        profile = chat["creator_profile"] if creator else chat["partner_profile"]
        items = (
            c.execute(
                select(rounds)
                .where(rounds.c.chat_id == chat_id)
                .order_by(rounds.c.created_at, rounds.c.id)
            )
            .mappings()
            .all()
        )
        history, active_round = [], None
        for item in items:
            sender = item["sender_user_id"] == self.user_id
            reveal = item["status"] == "completed"
            visible = sender or reveal
            content = item["content"] or {}
            public_messages = []
            for row in c.execute(
                select(messages)
                .where(messages.c.round_id == item["id"])
                .order_by(messages.c.created_at, messages.c.id)
            ).mappings():
                public_messages.append(
                    ChatMessage(
                        id=row["id"],
                        type=row["type"],
                        sender_id=row["sender_user_id"],
                        text=row["text"],
                        x=row["x"],
                        y=row["y"],
                        is_correct=None if row["is_correct"] is None else bool(row["is_correct"]),
                        created_at=row["created_at"],
                    )
                )

            def public_object(obj):
                return ChatObject(
                    **{key: value for key, value in obj.items() if key in ChatObject.model_fields}
                )

            stalled = bool(item["claim_id"] and item["claim_expires_at"] <= utc_now())
            shared = chat["status"] in {"waiting", "active"} and item["status"] != "cancelled"
            image_visible = (
                shared
                and (sender or item["status"] not in {"selectingTarget", "composingClue"})
                and item["photo_status"] == "ready"
            )
            result = ChatRound(
                id=item["id"],
                sender_id=item["sender_user_id"],
                status=item["status"],
                photo_status="failed" if stalled else item["photo_status"],
                image_url=f"/api/v1/friend-chats/{chat_id}/rounds/{item['id']}/image?width=640"
                if image_visible
                else None,
                created_at=item["created_at"],
                completed_at=item["completed_at"],
                objects=[public_object(obj) for obj in content.get("objects", [])]
                if visible and shared
                else [],
                target=public_object(item["target"])
                if visible and shared and item["target"]
                else None,
                clue_options=[
                    _public_clue_option(option) for option in item["clue_options"]
                ]
                if sender and shared
                else [],
                messages=public_messages,
                error=("Photo preparation stopped. Try again." if stalled else item["error"])
                if sender
                else None,
                retryable=sender
                and (stalled or (item["photo_status"] == "failed" and item["retryable"]))
                and item["analysis_attempts"] < 3,
            )
            if item["status"] in TERMINAL:
                history.append(result)
            else:
                active_round = result
        invite_status = chat["invite_status"]
        if invite_status == "open" and chat["invite_expires_at"] <= utc_now():
            invite_status = "expired"
        return ChatSnapshot(
            id=chat_id,
            status=chat["status"],
            revision=chat["revision"],
            me_id=self.user_id,
            target_language_code=chat["target_language_code"],
            viewer_level=profile["proficiency_level"],
            partner=self._person(c, other_id) if other_id else None,
            creator=self._person(c, chat["creator_user_id"]),
            invite_status=invite_status,
            created_at=chat["created_at"],
            updated_at=chat["updated_at"],
            active_round=active_round,
            rounds=history,
        )
