"""Server-only Storage access; upload capabilities never allow overwrites."""

from urllib.parse import quote, urlsplit

import httpx

from app.schemas.media import MAX_IMAGE_BYTES
from app.services.media_urls import MediaUrlError, PrivateMediaUrls


class InvalidImageUpload(Exception):
    pass


class UploadObjectMissing(Exception):
    pass


class ImageStorage:
    def __init__(self, project_url: str, service_key: str) -> None:
        self.url = project_url.rstrip("/") + "/storage/v1"
        self.headers = {"apikey": service_key}
        if not service_key.startswith("sb_"):
            self.headers["Authorization"] = f"Bearer {service_key}"
        self.signer = PrivateMediaUrls(project_url, "media-assets", service_key)
        self.configured = project_url.startswith("https://") and bool(service_key)

    def _check(self):
        if not self.configured:
            raise MediaUrlError("Storage is not configured.")

    def upload_url(self, key: str) -> str:
        self._check()
        try:
            response = httpx.post(
                f"{self.url}/object/upload/sign/media-assets/{quote(key, safe='/')}",
                headers=self.headers,
                json={},
                timeout=15,
            )
            response.raise_for_status()
            path = response.json()["url"]
            if not isinstance(path, str) or not path.startswith("/object/upload/sign/"):
                raise ValueError("Invalid upload URL")
            return self.url + path
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise MediaUrlError("Unable to create upload URL.") from exc

    def download(self, key: str) -> bytes:
        self._check()
        try:
            with httpx.stream(
                "GET",
                f"{self.url}/object/media-assets/{quote(key, safe='/')}",
                headers=self.headers,
                timeout=30,
            ) as response:
                if response.status_code == 404:
                    raise UploadObjectMissing()
                if response.status_code == 400:
                    response.read()
                    if (
                        response.json().get("error") in ("not_found", "Object not found")
                        or response.json().get("code") == "NoSuchKey"
                    ):
                        raise UploadObjectMissing()
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise InvalidImageUpload("Image exceeds 10 MB.")
                return bytes(data)
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaUrlError("Unable to inspect uploaded image.") from exc

    def download_url(self, url: str) -> bytes:
        # Public originals: no service-key headers, so nothing leaks to third-party hosts.
        self._check()
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
            raise MediaUrlError("Refusing to download a non-HTTP image URL.")
        try:
            with httpx.stream("GET", url, timeout=30) as response:
                if response.status_code == 404:
                    raise UploadObjectMissing()
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise InvalidImageUpload("Image exceeds 10 MB.")
                return bytes(data)
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaUrlError("Unable to inspect hosted image.") from exc

    def put(self, key: str, data: bytes, content_type: str) -> None:
        # Derivatives are regenerable, so overwrite is safe here unlike user uploads.
        self._check()
        try:
            response = httpx.post(
                f"{self.url}/object/media-assets/{quote(key, safe='/')}",
                headers={
                    **self.headers,
                    "content-type": content_type,
                    "x-upsert": "true",
                    "cache-control": "31536000",
                },
                content=data,
                timeout=15,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MediaUrlError("Unable to store derived image.") from exc

    def delete(self, key: str) -> None:
        self._check()
        try:
            response = httpx.request(
                "DELETE",
                f"{self.url}/object/media-assets",
                headers=self.headers,
                json={"prefixes": [key]},
                timeout=15,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MediaUrlError("Unable to remove invalid upload; retry confirmation.") from exc

    def read_url(self, key: str) -> str:
        url = self.signer.resolve([key]).get(key)
        if not url:
            raise MediaUrlError("Image URL unavailable.")
        return url
