"""Tests for the OpenAI image-moderation adapter."""

import json

import httpx
import pytest

from app.ai.features.moderation import (
    ImageModerationError,
    OpenAIImageModerator,
)
from app.services.vision_model import VisionImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 16
FAKE_API_KEY = "test-key-123"


def image() -> VisionImage:
    return VisionImage(data=PNG_BYTES, mime_type="image/png")


def moderator(handler) -> OpenAIImageModerator:
    return OpenAIImageModerator(
        api_key=FAKE_API_KEY,
        model_name="test-moderation-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_flagged_result_and_request_body() -> None:
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        captured["authorization"] = req.headers["Authorization"]
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"violence": True, "sexual": False},
                        "category_scores": {"violence": 0.9},
                    }
                ]
            },
        )

    result = moderator(handler).moderate(image())

    assert result.flagged is True
    assert result.categories == ("violence",)
    assert captured["authorization"] == f"Bearer {FAKE_API_KEY}"
    assert captured["url"].endswith("/moderations")
    body = captured["body"]
    assert body["model"] == "test-moderation-model"
    entry = body["input"][0]
    assert entry["type"] == "image_url"
    assert entry["image_url"]["url"].startswith("data:image/png;base64,")


def test_unflagged_result() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"flagged": False, "categories": {}}]},
        )

    result = moderator(handler).moderate(image())

    assert result.flagged is False
    assert result.categories == ()


@pytest.mark.parametrize("status_code", [400, 401, 429, 500])
def test_http_error_raises_moderation_error(status_code: int) -> None:
    secret = "provider-secret-payload"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=f"failure {secret}")

    with pytest.raises(ImageModerationError) as raised:
        moderator(handler).moderate(image())

    assert secret not in str(raised.value)
    assert FAKE_API_KEY not in str(raised.value)


def test_malformed_body_raises_moderation_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(ImageModerationError):
        moderator(handler).moderate(image())

    def non_json(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(ImageModerationError):
        moderator(non_json).moderate(image())


def test_provider_outage_raises_moderation_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=req)

    with pytest.raises(ImageModerationError):
        moderator(handler).moderate(image())


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAIImageModerator("", "model")
