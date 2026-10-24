"""Environment configuration for the temporary demo integration."""

import os
from pathlib import Path
from uuid import UUID

from app.services.media_urls import PrivateMediaUrls, SignedUrlCache

DEFAULT_DEMO_USER_ID = "11111111-1111-4111-8111-111111111111"


def get_media_public_base_url() -> str | None:
    return os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip() or None


_SIGNED_URL_CACHE = SignedUrlCache()


def get_private_media_urls() -> PrivateMediaUrls | None:
    if os.getenv("MEDIA_STORAGE_PRIVATE", "false").strip().lower() != "true":
        return None
    return PrivateMediaUrls(
        os.getenv("SUPABASE_URL", "").strip(),
        os.getenv("MEDIA_STORAGE_BUCKET", "media-assets").strip(),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        cache=_SIGNED_URL_CACHE,
    )


def get_demo_user_id() -> UUID:
    return UUID(os.getenv("DEMO_USER_ID", DEFAULT_DEMO_USER_ID))


def get_allowed_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]


# The packs bundled with the app, discovered when no pack folders are configured.
BUNDLED_LANGUAGE_PACKS = Path(__file__).parent / "language_packs" / "packs"


def get_language_pack_dirs() -> tuple[Path, ...]:
    """Configured pack folders, or the bundled packs when none are set."""
    configured = tuple(
        Path(value.strip())
        for value in os.getenv("LINGUINI_LANGUAGE_PACK_DIRS", "").split(os.pathsep)
        if value.strip()
    )
    return configured or (BUNDLED_LANGUAGE_PACKS,)


def get_language_pack_register() -> str:
    return os.getenv("LINGUINI_LANGUAGE_PACK_REGISTER", "everyday").strip()


def get_language_pack_experimental() -> bool:
    """Explicit local experiment; never permits experiments in production."""
    return (
        os.getenv("APP_ENV", "production").lower() in {"local", "development", "test"}
        and os.getenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "false").lower() == "true"
    )


def get_language_pack_releases() -> frozenset[tuple[str, str, str]]:
    releases = set()
    for value in os.getenv("LINGUINI_LANGUAGE_PACK_RELEASES", "").split(","):
        parts = tuple(part.strip() for part in value.split(":"))
        if len(parts) == 3 and all(parts):
            releases.add(parts)
    return frozenset(releases)


def get_stripe_secret_key() -> str | None:
    return os.getenv("STRIPE_SECRET_KEY", "").strip() or None


def get_stripe_publishable_key() -> str | None:
    return os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip() or None


def get_stripe_webhook_secret() -> str | None:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip() or None


def get_stripe_plus_price_id() -> str:
    return os.getenv("STRIPE_PLUS_PRICE_ID", "price_1URlZbBYwPhACwEB6goOgtNn").strip()


def get_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
