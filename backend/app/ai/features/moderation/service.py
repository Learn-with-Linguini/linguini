"""OpenAI adapter for upload-image moderation.

Sends the image to the Moderations API as a base64 data URI. Provider response
bodies are never surfaced in errors or logs — the session only learns that the
image was rejected or that moderation was unavailable.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.services.vision_model import VisionImage
from app.services.vision_openai import DEFAULT_OPENAI_BASE_URL

logger = logging.getLogger(__name__)


class ImageModerationError(RuntimeError):
    """The moderation provider could not deliver a usable verdict."""


@dataclass(frozen=True)
class ImageModerationResult:
    flagged: bool
    categories: tuple[str, ...] = ()


class ImageModerator(Protocol):
    def moderate(self, image: VisionImage) -> ImageModerationResult: ...


class OpenAIImageModerator:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        timeout_seconds: int = 30,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def moderate(self, image: VisionImage) -> ImageModerationResult:
        start = time.monotonic()
        image_data = base64.b64encode(image.data).decode("ascii")
        try:
            response = self._client.post(
                f"{self._base_url}/moderations",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model_name,
                    "input": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{image.mime_type};base64,{image_data}"
                                )
                            },
                        }
                    ],
                },
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError:
            self._log_error("providerRequestFailed", start)
            raise ImageModerationError(
                "image moderation request failed"
            ) from None

        if response.status_code >= 400:
            self._log_error("providerHttpError", start, response.status_code)
            raise ImageModerationError("image moderation provider request failed")

        try:
            body = response.json()
        except ValueError:
            self._log_error("providerResponseInvalid", start)
            raise ImageModerationError(
                "image moderation provider returned a non-JSON response"
            ) from None

        try:
            result = body["results"][0]
        except (KeyError, IndexError, TypeError):
            self._log_error("providerResponseInvalid", start)
            raise ImageModerationError(
                "image moderation provider returned an unusable response"
            ) from None
        if not isinstance(result, dict) or not isinstance(
            result.get("flagged"), bool
        ):
            self._log_error("providerResponseInvalid", start)
            raise ImageModerationError(
                "image moderation provider returned an unusable response"
            )
        categories = tuple(
            sorted(
                key
                for key, value in (result.get("categories") or {}).items()
                if value
            )
        )
        return ImageModerationResult(flagged=result["flagged"], categories=categories)

    def _log_error(
        self, code: str, start: float, status_code: int | None = None
    ) -> None:
        logger.warning(
            "image moderation provider error",
            extra={
                "code": code,
                "status_code": status_code,
                "model": self._model_name,
                "latency_seconds": round(time.monotonic() - start, 3),
            },
        )
