"""User queries against the table managed by Prisma migrations."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import read_connection
from app.repositories.users import UserRepositoryError
from app.schemas.users import UpdateUserRequest, User

# Query metadata only: never call create_all; schema changes belong in Prisma.
users = Table(
    "users",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("auth_provider_id", Text, nullable=False),
    Column("display_name", String(100), nullable=False),
    Column("email", String(320)),
    Column("timezone", Text, nullable=False),
    Column("learning_goal", String(300), nullable=False),
    Column("microphone_enabled", Boolean, nullable=False),
    Column("camera_enabled", Boolean, nullable=False),
    Column("onboarding_completed", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


class PostgresUserRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_or_create_by_auth_provider(
        self, auth_provider_id: str, email: str | None
    ) -> User:
        existing = self.get_by_auth_provider_id(auth_provider_id)
        if existing is not None:
            return existing
        display_name = (email or "").split("@", 1)[0][:100] or "Learner"
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        insert(users)
                        .values(
                            auth_provider_id=auth_provider_id,
                            display_name=display_name,
                            email=email,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[users.c.auth_provider_id]
                        )
                        .returning(users)
                    )
                    .mappings()
                    .one_or_none()
                )
            if row is not None:
                return User.model_validate(dict(row))
            created = self.get_by_auth_provider_id(auth_provider_id)
            if created is None:
                raise UserRepositoryError("Unable to provision the authenticated user.")
            return created
        except (SQLAlchemyError, ValidationError) as exc:
            raise UserRepositoryError("Unable to save user.") from exc

    def get_by_auth_provider_id(self, auth_provider_id: str) -> User | None:
        try:
            with read_connection(self.engine) as connection:
                row = (
                    connection.execute(
                        select(users).where(
                            users.c.auth_provider_id == auth_provider_id
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return User.model_validate(dict(row)) if row is not None else None
        except (SQLAlchemyError, ValidationError) as exc:
            raise UserRepositoryError("Unable to load user.") from exc

    def get_by_id(self, user_id: UUID) -> User | None:
        try:
            with read_connection(self.engine) as connection:
                row = (
                    connection.execute(select(users).where(users.c.id == user_id))
                    .mappings()
                    .one_or_none()
                )
                return User.model_validate(dict(row)) if row is not None else None
        except (SQLAlchemyError, ValidationError) as exc:
            raise UserRepositoryError("Unable to load user.") from exc

    def update(self, user_id: UUID, request: UpdateUserRequest) -> User | None:
        values = request.model_dump(exclude_unset=True, exclude_none=True, by_alias=False)
        if not values:
            return self.get_by_id(user_id)
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        update(users).where(users.c.id == user_id).values(**values).returning(users)
                    )
                    .mappings()
                    .one_or_none()
                )
                return User.model_validate(dict(row)) if row is not None else None
        except (SQLAlchemyError, ValidationError) as exc:
            raise UserRepositoryError("Unable to save user.") from exc
