import json

import httpx
import pytest

from app.ai.features.scene_analysis import (
    SCENE_ANALYSIS_PROMPT_VERSION,
    SceneAnalysisModelResult,
)
from app.services.vision_model import (
    VisionImage,
    VisionModelConfig,
    VisionModelError,
    VisionModelErrorCode,
    VisionModelRequest,
    build_strict_json_schema,
)
from app.services.vision_openai import OpenAIVisionClient, build_vision_client

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 16
FAKE_API_KEY = "test-key-123"

VALID_OUTPUT = json.dumps(
    {
        "suggestedSceneTitle": "Kitchen",
        "objects": [
            {
                "objectKey": "object_1",
                "label": "chair",
                "boundingBox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "attributes": [{"type": "color", "value": "red"}],
                "confidenceScore": 0.9,
            }
        ],
        "relations": [],
    }
)


def image() -> VisionImage:
    return VisionImage(data=PNG_BYTES, mime_type="image/png")


def config(**overrides) -> VisionModelConfig:
    values = {"model_name": "test-vision-model", "max_retries": 1}
    values.update(overrides)
    return VisionModelConfig(**values)


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


def adapter(
    handler, cfg: VisionModelConfig | None = None
) -> OpenAIVisionClient:
    return OpenAIVisionClient(
        api_key=FAKE_API_KEY,
        config=cfg or config(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def request() -> VisionModelRequest:
    return VisionModelRequest(
        image=image(),
        system_prompt="sys",
        user_instruction="user",
        json_schema_name="scene_analysis_v2",
        json_schema=build_strict_json_schema(SceneAnalysisModelResult),
        prompt_version=SCENE_ANALYSIS_PROMPT_VERSION,
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
    assert response.prompt_version == SCENE_ANALYSIS_PROMPT_VERSION
    assert response.input_tokens == 100
    assert captured["authorization"] == f"Bearer {FAKE_API_KEY}"

    body = captured["body"]
    assert body["model"] == "test-vision-model"
    assert body["max_output_tokens"] == 1500
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "scene_analysis_v2"
    assert fmt["schema"]["additionalProperties"] is False

    user_content = body["input"][1]["content"]
    assert user_content[0] == {"type": "input_text", "text": "user"}
    assert user_content[1]["type"] == "input_image"
    assert user_content[1]["image_url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (429, VisionModelErrorCode.PROVIDER_RATE_LIMITED),
        (401, VisionModelErrorCode.PROVIDER_AUTH),
        (403, VisionModelErrorCode.PROVIDER_AUTH),
        (500, VisionModelErrorCode.PROVIDER_UNAVAILABLE),
        (400, VisionModelErrorCode.PROVIDER_ERROR),
    ],
)
def test_adapter_maps_http_errors(status_code: int, expected: VisionModelErrorCode) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "nope"}})

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == expected


def test_adapter_timeout_maps_to_provider_timeout() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=req)

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == VisionModelErrorCode.PROVIDER_TIMEOUT
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

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == VisionModelErrorCode.PROVIDER_REFUSED


def test_adapter_incomplete_content_filter_is_refusal() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "content_filter"},
                "output": [],
            },
        )

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == VisionModelErrorCode.PROVIDER_REFUSED


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

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == VisionModelErrorCode.PROVIDER_RESPONSE_INVALID


def test_adapter_empty_output_is_response_invalid() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "output": []})

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert raised.value.code == VisionModelErrorCode.PROVIDER_RESPONSE_INVALID


def test_adapter_accepts_top_level_output_text() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "completed", "output": [], "output_text": VALID_OUTPUT},
        )

    response = adapter(handler).generate(request())

    assert response.output_text == VALID_OUTPUT


def test_vision_image_rejects_disallowed_inputs() -> None:
    with pytest.raises(VisionModelError) as raised:
        VisionImage(data=PNG_BYTES, mime_type="image/gif")
    assert raised.value.code == VisionModelErrorCode.INVALID_IMAGE

    with pytest.raises(VisionModelError):
        VisionImage(data=b"", mime_type="image/png")

    with pytest.raises(VisionModelError):
        VisionImage(data=b"x" * (10 * 1024 * 1024 + 1), mime_type="image/png")


def test_no_remote_url_code_path() -> None:
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return provider_response()

    adapter(handler).generate(request())
    image_url = captured["body"]["input"][1]["content"][1]["image_url"]
    assert image_url.startswith("data:")


def test_error_hygiene_no_provider_body_or_key_leak() -> None:
    secret = "sk-should-never-appear-xyz"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"failure {secret}")

    with pytest.raises(VisionModelError) as raised:
        adapter(handler).generate(request())

    assert secret not in str(raised.value)
    assert FAKE_API_KEY not in str(raised.value)


def test_config_validation() -> None:
    with pytest.raises(ValueError, match="at most once"):
        VisionModelConfig(model_name="m", max_retries=2)
    with pytest.raises(ValueError):
        VisionModelConfig(model_name="m", timeout_seconds=0)
    with pytest.raises(ValueError):
        VisionModelConfig(model_name="m", max_output_tokens=0)


def test_build_vision_client_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown vision provider"):
        build_vision_client("gemini", FAKE_API_KEY, config())
