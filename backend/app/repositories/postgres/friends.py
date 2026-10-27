"""Mutual friends created only by an explicitly accepted private invitation."""

import hashlib
import secrets
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.room_errors import RoomError
from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.friends import FriendInvite, FriendPublic
from app.services.room_languages import room_profile_supported

metadata = MetaData()
friendships = Table(
    "friendships",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_low_id", Uuid, nullable=False),
    Column("user_high_id", Uuid, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
friend_invitations = Table(
    "friend_invitations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_user_id", Uuid, nullable=False),
    Column("command_id", Uuid, nullable=False),
    Column("invite_code", String(64), nullable=False),
    Column("invite_hash", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("accepted_user_id", Uuid),
    Column("accepted_command_id", Uuid),
    Column("accepted_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
INVITE_DURATION = timedelta(days=7)


def friendship_condition(user_id, friend_id):
    low, high = sorted((user_id, friend_id))
    return (friendships.c.user_low_id == low) & (friendships.c.user_high_id == high)


def compatible_profile(profile):
    return room_profile_supported(profile)


def matching_profiles(first, second):
    return (
        compatible_profile(first)
        and compatible_profile(second)
        and all(
            first[field].lower() == second[field].lower()
            for field in ("source_language_code", "target_language_code", "proficiency_level")
        )
    )


class PostgresFriendRepository:
    def __init__(self, engine, user_id):
        self.engine, self.user_id = engine, user_id

    @contextmanager
    def _locked(self, other_user_id=None):
        try:
            with self.engine.begin() as c:
                ids = {self.user_id, other_user_id} - {None}
                locked = set(
                    c.execute(
                        select(users.c.id)
                        .where(users.c.id.in_(ids))
                        .order_by(users.c.id)
                        .with_for_update()
                    ).scalars()
                )
                if self.user_id not in locked:
                    raise RoomError("friend_unauthenticated", "Sign in to add friends.", 401)
                if other_user_id and other_user_id not in locked:
                    raise RoomError(
                        "friend_invite_invalid", "This friend invitation is unavailable.", 404
                    )
                yield c
        except SQLAlchemyError as exc:
            raise RoomError(
                "friend_storage_error", "Friends could not be saved. Try again.", 503
            ) from exc

    def invite(self, request):
        with self._locked() as c:
            existing = (
                c.execute(
                    select(friend_invitations).where(
                        friend_invitations.c.owner_user_id == self.user_id,
                        friend_invitations.c.command_id == request.command_id,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                return FriendInvite(
                    invite_code=existing["invite_code"], expires_at=existing["expires_at"]
                )
            recent = c.execute(
                select(func.count())
                .select_from(friend_invitations)
                .where(
                    friend_invitations.c.owner_user_id == self.user_id,
                    friend_invitations.c.created_at > utc_now() - timedelta(hours=1),
                )
            ).scalar_one()
            if recent >= 10:
                raise RoomError(
                    "friend_rate_limited", "You've made several invitations. Try again later.", 429
                )
            code, now = secrets.token_hex(32), utc_now()
            expires = now + INVITE_DURATION
            c.execute(
                insert(friend_invitations).values(
                    id=uuid4(),
                    owner_user_id=self.user_id,
                    command_id=request.command_id,
                    invite_code=code,
                    invite_hash=hashlib.sha256(code.encode()).hexdigest(),
                    expires_at=expires,
                    created_at=now,
                )
            )
            return FriendInvite(invite_code=code, expires_at=expires)

    def accept(self, request):
        hashed = hashlib.sha256(request.invite_code.encode()).hexdigest()
        with self.engine.connect() as c:
            owner_id = c.execute(
                select(friend_invitations.c.owner_user_id).where(
                    friend_invitations.c.invite_hash == hashed,
                )
            ).scalar_one_or_none()
        if owner_id is None:
            raise RoomError("friend_invite_invalid", "This friend invitation is unavailable.", 404)
        with self._locked(owner_id) as c:
            invitation = (
                c.execute(
                    select(friend_invitations)
                    .where(
                        friend_invitations.c.invite_hash == hashed,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if invitation is None:
                raise RoomError(
                    "friend_invite_invalid", "This friend invitation is unavailable.", 404
                )
            if owner_id == self.user_id:
                raise RoomError("friend_invite_self", "Share this invitation with a friend.", 422)
            prior = c.execute(
                select(friend_invitations.c.id).where(
                    friend_invitations.c.accepted_user_id == self.user_id,
                    friend_invitations.c.accepted_command_id == request.command_id,
                )
            ).scalar_one_or_none()
            if prior and prior != invitation["id"]:
                raise RoomError(
                    "friend_command_conflict", "This action key was used for another invitation."
                )
            if invitation["accepted_at"]:
                if invitation["accepted_user_id"] != self.user_id:
                    raise RoomError(
                        "friend_invite_used",
                        "This friend invitation has already been accepted.",
                        410,
                    )
                if not c.execute(
                    select(friendships.c.id).where(
                        friendship_condition(self.user_id, owner_id),
                    )
                ).first():
                    raise RoomError(
                        "friend_invite_used", "Use a new invitation to add this friend again.", 410
                    )
                return self._public(c, owner_id)
            if invitation["expires_at"] <= utc_now():
                raise RoomError("friend_invite_expired", "This friend invitation has expired.", 410)
            recent = c.execute(
                select(func.count())
                .select_from(friend_invitations)
                .where(
                    friend_invitations.c.accepted_user_id == self.user_id,
                    friend_invitations.c.accepted_at > utc_now() - timedelta(hours=1),
                )
            ).scalar_one()
            if recent >= 20:
                raise RoomError(
                    "friend_rate_limited", "You've added several friends. Try again later.", 429
                )
            low, high = sorted((self.user_id, owner_id))
            c.execute(
                pg_insert(friendships)
                .values(
                    id=uuid4(),
                    user_low_id=low,
                    user_high_id=high,
                    created_at=utc_now(),
                )
                .on_conflict_do_nothing(
                    index_elements=[friendships.c.user_low_id, friendships.c.user_high_id]
                )
            )
            c.execute(
                update(friend_invitations)
                .where(friend_invitations.c.id == invitation["id"])
                .values(
                    accepted_user_id=self.user_id,
                    accepted_command_id=request.command_id,
                    accepted_at=utc_now(),
                )
            )
            return self._public(c, owner_id)

    @staticmethod
    def _active_profile(c, user_id):
        return (
            c.execute(
                select(language_profiles).where(
                    language_profiles.c.user_id == user_id,
                    language_profiles.c.is_active.is_(True),
                )
            )
            .mappings()
            .first()
        )

    def _public(self, c, friend_id):
        person = c.execute(select(users.c.display_name).where(users.c.id == friend_id)).scalar_one()
        profile = self._active_profile(c, friend_id)
        mine = self._active_profile(c, self.user_id)
        return FriendPublic(
            user_id=friend_id,
            display_name=person,
            source_language_code=profile["source_language_code"] if profile else None,
            target_language_code=profile["target_language_code"] if profile else None,
            proficiency_level=profile["proficiency_level"] if profile else None,
            can_challenge=matching_profiles(mine, profile),
        )

    def list(self):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            links = c.execute(
                select(friendships)
                .where(
                    or_(
                        friendships.c.user_low_id == self.user_id,
                        friendships.c.user_high_id == self.user_id,
                    )
                )
                .order_by(friendships.c.created_at)
            ).mappings()
            return [
                self._public(
                    c,
                    row["user_high_id"]
                    if row["user_low_id"] == self.user_id
                    else row["user_low_id"],
                )
                for row in links
            ]

    def remove(self, friend_id):
        with self._locked() as c:
            c.execute(delete(friendships).where(friendship_condition(self.user_id, friend_id)))
