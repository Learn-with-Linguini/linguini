"""Irreversible deletion of a learner's data, media, and auth identity."""

from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.rooms import cleanup_room_account
from app.repositories.postgres.users import users
from app.services.image_derivatives import ALLOWED_WIDTHS, DERIVATIVE_ROOT
from app.services.image_storage import ImageStorage
from app.services.media_urls import MediaUrlError


class AccountDeletionError(Exception):
    """The account could not be completely deleted."""


class AccountDeletionNotConfiguredError(AccountDeletionError):
    """Server-side Supabase administration is unavailable."""


class SupabaseAuthAdmin:
    """Small server-only client for checking and deleting Auth identities."""

    def __init__(self, project_url: str, service_key: str) -> None:
        self.url = project_url.rstrip("/")
        self.headers = {"apikey": service_key}
        if not service_key.startswith("sb_"):
            self.headers["Authorization"] = f"Bearer {service_key}"
        self.configured = self.url.startswith("https://") and bool(service_key)

    def user_exists(self, auth_provider_id: str) -> bool:
        if not self.configured:
            raise AccountDeletionNotConfiguredError(
                "Supabase Auth administration is not configured on this server."
            )
        try:
            response = httpx.get(
                f"{self.url}/auth/v1/admin/users/{quote(auth_provider_id, safe='')}",
                headers=self.headers,
                timeout=15,
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            raise AccountDeletionError(
                "Unable to confirm the sign-in account."
            ) from exc

    def delete_user(self, auth_provider_id: str) -> None:
        if not self.configured:
            raise AccountDeletionNotConfiguredError(
                "Account deletion is not configured on this server."
            )
        try:
            response = httpx.delete(
                f"{self.url}/auth/v1/admin/users/{quote(auth_provider_id, safe='')}",
                headers=self.headers,
                timeout=15,
            )
            # A missing auth identity is already in the desired state.
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AccountDeletionError("Unable to remove the sign-in account.") from exc


class AccountDeletionService:
    """Delete every user-owned record while retaining shared catalogue data."""

    def __init__(
        self,
        engine: Engine,
        storage: ImageStorage,
        auth_admin: SupabaseAuthAdmin,
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.auth_admin = auth_admin

    def delete_account(self, user_id: UUID, auth_provider_id: str) -> None:
        if not self.auth_admin.configured:
            raise AccountDeletionNotConfiguredError(
                "Account deletion is not configured on this server."
            )

        try:
            with self.engine.begin() as connection:
                stored_identity = connection.execute(
                    select(users.c.auth_provider_id)
                    .where(users.c.id == user_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if stored_identity is None:
                    return
                if stored_identity != auth_provider_id:
                    raise AccountDeletionError("The authenticated account does not match.")

                if not self.storage.configured:
                    raise AccountDeletionNotConfiguredError(
                        "Media deletion is not configured on this server."
                    )
                image_prefix = f"users/{user_id}/images"
                cleanup_room_account(connection, user_id)
                self.storage.delete_prefixes(
                    [
                        image_prefix,
                        # Keep deleting the pre-orientation cache as well as the
                        # current cache, so account deletion removes every copy.
                        *(f"derived/w{width}/{image_prefix}" for width in ALLOWED_WIDTHS),
                        *(f"{DERIVATIVE_ROOT}/w{width}/{image_prefix}" for width in ALLOWED_WIDTHS),
                    ]
                )

                # Profiles own sessions and journals, which must disappear before
                # their referenced user-owned media assets can be removed.
                connection.execute(
                    delete(language_profiles).where(language_profiles.c.user_id == user_id)
                )
                connection.execute(
                    delete(media_assets).where(media_assets.c.owner_user_id == user_id)
                )
                deleted = connection.execute(
                    delete(users).where(users.c.id == user_id).returning(users.c.id)
                ).scalar_one_or_none()
                if deleted is None:
                    raise AccountDeletionError("The account no longer exists.")

                # Keep the transaction open until Auth accepts deletion. If Auth
                # fails, PostgreSQL rolls back so the learner can retry.
                self.auth_admin.delete_user(auth_provider_id)
        except AccountDeletionError:
            raise
        except MediaUrlError as exc:
            raise AccountDeletionError("Unable to remove uploaded media.") from exc
        except SQLAlchemyError as exc:
            raise AccountDeletionError("Unable to remove account data.") from exc
