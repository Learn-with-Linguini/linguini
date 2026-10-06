"""Environment configuration for the temporary demo integration."""

import os
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
