"""Resolve public media object URLs from a shared Storage bucket."""

import threading
import time
from urllib.parse import quote, urlsplit

import httpx


class MediaUrlError(Exception):
    pass


class SignedUrlCache:
    """Process-wide cache for signed URLs; TTL stays below the signed expiry."""

    def __init__(self, ttl_seconds: float = 3000.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str, str], tuple[str, float]] = {}

    def get(self, project_url: str, bucket: str, storage_key: str) -> str | None:
        key = (project_url, bucket, storage_key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            url, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._entries[key]
                return None
            return url

    def put(self, project_url: str, bucket: str, storage_key: str, url: str) -> None:
        with self._lock:
            self._entries[(project_url, bucket, storage_key)] = (
                url,
                time.monotonic() + self.ttl_seconds,
            )


class PrivateMediaUrls:
    """Sign only object keys already authorized by the calling service."""

    def __init__(
        self,
        project_url: str,
        bucket: str,
        service_key: str,
        cache: SignedUrlCache | None = None,
    ) -> None:
        self.project_url = project_url
        self.storage_url = project_url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.service_key = service_key
        self.cache = cache

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self.service_key}
        if not self.service_key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.service_key}"
        return headers

    def resolve(self, keys: list[str]) -> dict[str, str | None]:
        result = {key: public_media_url(key, None) for key in keys}
        paths = list(
            dict.fromkeys(
                key for key in keys if not key.startswith("demo-art/") and result[key] is None
            )
        )
        if self.cache is not None:
            for path in paths:
                cached = self.cache.get(self.project_url, self.bucket, path)
                if cached is not None:
                    result[path] = cached
            paths = [path for path in paths if result[path] is None]
        if not paths:
            return result
        parsed = urlsplit(self.project_url)
        if not self.service_key or not self.bucket or parsed.scheme != "https" or not parsed.netloc:
            raise MediaUrlError("Private media signing is not configured.")
        try:
            response = httpx.post(
                f"{self.storage_url}/object/sign/{quote(self.bucket, safe='')}",
                headers=self._headers(),
                json={"paths": paths, "expiresIn": 3600},
                timeout=15,
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError("Invalid signing response")
            for row in rows:
                path = row["path"]
                signed = row.get("signedURL")
                if path not in paths or row.get("error") or not isinstance(signed, str):
                    raise ValueError("Unable to sign an object")
                if not signed.startswith("/object/sign/"):
                    raise ValueError("Invalid signed URL")
                result[path] = self.storage_url + quote(signed, safe="/%?=&")
            if any(result[path] is None for path in paths):
                raise ValueError("Missing signed URL")
            if self.cache is not None:
                for path in paths:
                    self.cache.put(self.project_url, self.bucket, path, result[path])
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Never expose Storage responses, credentials, or signed tokens to API errors.
            raise MediaUrlError("Unable to sign media URLs.") from exc


def public_media_url(storage_key: str, public_base_url: str | None) -> str | None:
    # Seeded demo illustrations are rendered locally, not stored in Supabase.
    if storage_key.startswith("demo-art/"):
        return None
    parsed = urlsplit(storage_key)
    if parsed.scheme in ("https", "http") and parsed.netloc:
        return storage_key
    if parsed.scheme or storage_key.startswith("//") or not public_base_url:
        return None
    # Keys are raw, bucket-relative object paths. Encode spaces, #, ?, and Unicode.
    return f"{public_base_url.rstrip('/')}/{quote(storage_key.lstrip('/'), safe='/')}"
