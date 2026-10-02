"""Temperature is configurable per feature and defaults to deterministic zero."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from app.ai.text_model import TextModelConfig, TextModelRequest
from app.ai.text_openai import OpenAITextClient
from app.services.vision_model import VisionImage, VisionModelConfig, VisionModelRequest
from app.services.vision_openai import OpenAIVisionClient

SCHEMA = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}


def text_request():
    return TextModelRequest(
        system_prompt="system", user_content="{}", json_schema_name="s",
        json_schema=SCHEMA, prompt_version="v1",
    )


def http_client(body):
    transport = MagicMock(
        return_value=httpx.Response(200, json=body, request=httpx.Request("POST", "http://x"))
    )
    return httpx.Client(transport=httpx.MockTransport(lambda request: transport(request)))


def response_body():
    return {
        "output": [{"content": [{"type": "output_text", "text": "{}"}]}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def sent_body(client_config, request, *, vision=False):
    captured = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(http_request.content))
        return httpx.Response(200, json=response_body())

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    cls = OpenAIVisionClient if vision else OpenAITextClient
    cls("key", client_config, client=http).generate(request)
    return captured


def test_text_default_is_deterministic():
    assert TextModelConfig(model_name="m").temperature == 0.0
    body = sent_body(TextModelConfig(model_name="m"), text_request())
    assert body["temperature"] == 0.0


def test_text_temperature_is_sent_when_configured():
    body = sent_body(TextModelConfig(model_name="m", temperature=0.7), text_request())
    assert body["temperature"] == 0.7


def test_vision_temperature_is_sent_when_configured():
    request = VisionModelRequest(
        image=VisionImage(data=b"\xff\xd8\xff", mime_type="image/jpeg"),
        system_prompt="system", user_instruction="describe", json_schema_name="s",
        json_schema=SCHEMA, prompt_version="v1",
    )

    body = sent_body(
        VisionModelConfig(model_name="m", temperature=0.4), request, vision=True
    )

    assert body["temperature"] == 0.4


@pytest.mark.parametrize("value", [-0.1, 2.1])
def test_temperature_outside_the_supported_range_is_rejected(value):
    with pytest.raises(ValueError):
        TextModelConfig(model_name="m", temperature=value)
    with pytest.raises(ValueError):
        VisionModelConfig(model_name="m", temperature=value)


def test_gemini_text_client_sends_the_configured_temperature():
    from app.ai.text_gemini import GeminiTextClient

    captured = {}

    def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="{}", candidates=[SimpleNamespace(finish_reason=None)], usage_metadata=None
        )

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    GeminiTextClient(
        "key", TextModelConfig(model_name="m", temperature=0.3), client=client
    ).generate(text_request())

    assert captured["config"].temperature == 0.3
