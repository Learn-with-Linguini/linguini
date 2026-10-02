import json

import httpx
import pytest

from app.ai.features.translation import (
    SCENE_TRANSLATION_PROMPT_VERSION,
    build_scene_translation_schema,
)
from app.ai.model_errors import ProviderError, ProviderErrorCode
from app.ai.text_model import TextModelConfig, TextModelRequest
from app.ai.text_openai import OpenAITextClient

FAKE_API_KEY = "test-key-123"

VALID_OUTPUT = json.dumps({"objects": [], "attributes": [], "relationships": []})


def config(**overrides) -> TextModelConfig:
    values = {"model_name": "test-text-model", "max_retries": 1}
    values.update(overrides)
    return TextModelConfig(**values)


def provider_response(text: str = VALID_OUTPUT) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    )


def adapter(handler, cfg: TextModelConfig | None = None) -> OpenAITextClient:
    return OpenAITextClient(
        api_key=FAKE_API_KEY,
        config=cfg or config(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def request() -> TextModelRequest:
    return TextModelRequest(
        system_prompt="sys",
        user_content='{"targetLanguage":"es"}',
        json_schema_name="scene_translation_v1",
        json_schema=build_scene_translation_schema(),
        prompt_version=SCENE_TRANSLATION_PROMPT_VERSION,
    )


def test_adapter_success_and_request_body() -> None:
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        captured["authorization"] = req.headers["Authorization"]
        return provider_response()

    client = adapter(handler)
    response = client.generate(request())

    assert response.output_text == VALID_OUTPUT
    assert response.prompt_version == SCENE_TRANSLATION_PROMPT_VERSION
    assert response.input_tokens == 100
    assert response.output_tokens == 50
    assert captured["authorization"] == f"Bearer {FAKE_API_KEY}"

    body = captured["body"]
    assert body["model"] == "test-text-model"
    assert body["temperature"] == 0
    assert body["max_output_tokens"] == 1500
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "scene_translation_v1"
    assert fmt["schema"]["additionalProperties"] is False

    user_content = body["input"][1]["content"]
    assert user_content == [
        {"type": "input_text", "text": '{"targetLanguage":"es"}'}
    ]


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (429, ProviderErrorCode.PROVIDER_RATE_LIMITED),
        (401, ProviderErrorCode.PROVIDER_AUTH),
        (403, ProviderErrorCode.PROVIDER_AUTH),
        (500, ProviderErrorCode.PROVIDER_UNAVAILABLE),
        (400, ProviderErrorCode.PROVIDER_ERROR),
    ],
)
def test_adapter_maps_http_errors(status_code: int, expected: ProviderErrorCode) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "nope"}})

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == expected


def test_adapter_timeout_maps_to_provider_timeout() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=req)

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == ProviderErrorCode.PROVIDER_TIMEOUT
    assert raised.value.transient


def test_adapter_refusal_content_part() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "cannot"}],
                    }
                ],
            },
        )

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == ProviderErrorCode.PROVIDER_REFUSED


def test_adapter_incomplete_max_tokens_is_response_invalid() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{\"partial\":"}],
                    }
                ],
            },
        )

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == ProviderErrorCode.PROVIDER_RESPONSE_INVALID


def test_adapter_empty_output_is_response_invalid() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "output": []})

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == ProviderErrorCode.PROVIDER_RESPONSE_INVALID


def test_error_hygiene_no_provider_body_or_key_leak() -> None:
    secret = "sk-should-never-appear-xyz"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"failure {secret}")

    with pytest.raises(ProviderError) as raised:
        adapter(handler).generate(request())

    assert secret not in str(raised.value)
    assert FAKE_API_KEY not in str(raised.value)


def test_config_validation() -> None:
    with pytest.raises(ValueError, match="at most once"):
        TextModelConfig(model_name="m", max_retries=2)
    with pytest.raises(ValueError):
        TextModelConfig(model_name="m", timeout_seconds=0)
    with pytest.raises(ValueError):
        TextModelConfig(model_name="m", max_output_tokens=0)
    with pytest.raises(ValueError):
        TextModelConfig(model_name="")


def test_requires_api_key() -> None:
    with pytest.raises(ValueError):
        OpenAITextClient("", config())
