"""Transactional language-profile persistence with per-user activation locking."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import read_connection
from app.repositories.language_profiles import (
    LanguageProfileConflictError,
    LanguageProfileNotFoundError,
    LanguageProfileStorageError,
)
from app.repositories.postgres.users import users
from app.schemas.users import LanguageProfile, UpdateLanguageProfileRequest

# Query metadata only; Prisma migrations own constraints and DDL.
language_profiles = Table(
    "language_profiles",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("source_language_code", String(35), nullable=False),
    Column("target_language_code", String(35), nullable=False),
    Column("proficiency_level", String(2), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("preferred_input_mode", String(6), nullable=False),
    Column("daily_goal_minutes", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


def lock_user(connection: Connection, user_id: UUID) -> None:
    # Lock the parent even when it has no profiles; all activation writers use this lock.
    found = connection.execute(
        select(users.c.id).where(users.c.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if found is None:
        raise LanguageProfileStorageError("The profile's user does not exist in PostgreSQL.")


def deactivate_other_profiles(connection: Connection, user_id: UUID, profile_id: UUID) -> None:
    connection.execute(
        update(language_profiles)
        .where(
            language_profiles.c.user_id == user_id,
            language_profiles.c.id != profile_id,
            language_profiles.c.is_active.is_(True),
        )
        .values(is_active=False)
    )


class PostgresLanguageProfileRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_for_user(self, user_id: UUID) -> list[LanguageProfile]:
        try:
            with read_connection(self.engine) as connection:
                rows = connection.execute(
                    select(language_profiles)
                    .where(language_profiles.c.user_id == user_id)
                    .order_by(language_profiles.c.created_at, language_profiles.c.id)
                ).mappings()
                return [LanguageProfile.model_validate(dict(row)) for row in rows]
        except (SQLAlchemyError, ValidationError) as exc:
            raise LanguageProfileStorageError("Unable to read language profiles.") from exc

    def create(self, profile: LanguageProfile) -> LanguageProfile:
        try:
            with self.engine.begin() as connection:
                lock_user(connection, profile.user_id)
                if profile.is_active:
                    deactivate_other_profiles(connection, profile.user_id, profile.id)
                row = (
                    connection.execute(
                        insert(language_profiles)
                        .values(**profile.model_dump(by_alias=False))
                        .returning(language_profiles)
                    )
                    .mappings()
                    .one()
                )
                return LanguageProfile.model_validate(dict(row))
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise LanguageProfileConflictError("This language profile already exists.") from exc
            raise LanguageProfileStorageError("Unable to save language profiles.") from exc
        except (SQLAlchemyError, ValidationError) as exc:
            raise LanguageProfileStorageError("Unable to save language profiles.") from exc

    def update(
        self, user_id: UUID, profile_id: UUID, request: UpdateLanguageProfileRequest
    ) -> LanguageProfile:
        patch = {
            key: value
            for key, value in request.model_dump(exclude_unset=True, by_alias=False).items()
            if value is not None or key == "daily_goal_minutes"
        }
        try:
            with self.engine.begin() as connection:
                lock_user(connection, user_id)
                condition = (language_profiles.c.user_id == user_id) & (
                    language_profiles.c.id == profile_id
                )
                existing = (
                    connection.execute(select(language_profiles).where(condition))
                    .mappings()
                    .one_or_none()
                )
                if existing is None:
                    raise LanguageProfileNotFoundError("Language profile not found.")
                if not patch:
                    return LanguageProfile.model_validate(dict(existing))
                if patch.get("is_active"):
                    deactivate_other_profiles(connection, user_id, profile_id)
                row = (
                    connection.execute(
                        update(language_profiles)
                        .where(condition)
                        .values(**patch)
                        .returning(language_profiles)
                    )
                    .mappings()
                    .one()
                )
                return LanguageProfile.model_validate(dict(row))
        except (SQLAlchemyError, ValidationError) as exc:
            raise LanguageProfileStorageError("Unable to save language profiles.") from exc
