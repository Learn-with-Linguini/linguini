import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.ai.features.translation import (
    SCENE_TRANSLATION_PROMPT_VERSION,
    build_scene_translation_schema,
)
from app.ai.model_errors import ProviderError, ProviderErrorCode
from app.ai.text_gemini import GeminiTextClient
from app.ai.text_model import TextModelConfig, TextModelRequest

FAKE_API_KEY = "test-key-123"

VALID_OUTPUT = json.dumps({"objects": [], "attributes": [], "relationships": []})


def config(**overrides) -> TextModelConfig:
    values = {"model_name": "test-text-model", "max_retries": 1}
    values.update(overrides)
    return TextModelConfig(**values)


def _response(**overrides):
    return SimpleNamespace(
        text=overrides.get("text", VALID_OUTPUT),
        prompt_feedback=overrides.get("prompt_feedback"),
        candidates=overrides.get(
            "candidates", [SimpleNamespace(finish_reason="STOP")]
        ),
        usage_metadata=overrides.get("usage_metadata"),
    )


def _request() -> TextModelRequest:
    return TextModelRequest(
        system_prompt="sys",
        user_content='{"targetLanguage":"es"}',
        json_schema_name="scene_translation_v1",
        json_schema=build_scene_translation_schema(),
        prompt_version=SCENE_TRANSLATION_PROMPT_VERSION,
    )


def _client_raising(error):
    class Models:
        def generate_content(self, **kwargs):
            raise error

    return GeminiTextClient(
        FAKE_API_KEY, config(), client=SimpleNamespace(models=Models())
    )


def _client_returning(response):
    class Models:
        def generate_content(self, **kwargs):
            return response

    return GeminiTextClient(
        FAKE_API_KEY, config(), client=SimpleNamespace(models=Models())
    )


def test_adapter_success_and_request_shape() -> None:
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured["kwargs"] = kwargs
            return _response(
                usage_metadata=SimpleNamespace(
                    prompt_token_count=100, candidates_token_count=50
                )
            )

    client = GeminiTextClient(
        FAKE_API_KEY, config(), client=SimpleNamespace(models=Models())
    )
    response = client.generate(_request())

    assert response.output_text == VALID_OUTPUT
    assert response.input_tokens == 100
    assert response.output_tokens == 50
    assert response.prompt_version == SCENE_TRANSLATION_PROMPT_VERSION

    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-text-model"
    assert kwargs["contents"] == ['{"targetLanguage":"es"}']
    gemini_config = kwargs["config"]
    assert gemini_config.system_instruction == "sys"
    assert gemini_config.temperature == 0
    assert gemini_config.response_mime_type == "application/json"
    assert gemini_config.response_json_schema == _request().json_schema
    assert gemini_config.max_output_tokens == 1500


def test_timeout_maps_to_provider_timeout() -> None:
    client = _client_raising(httpx.ReadTimeout("t"))
    with pytest.raises(ProviderError) as raised:
        client.generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_TIMEOUT
    assert raised.value.transient


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderErrorCode.PROVIDER_AUTH),
        (403, ProviderErrorCode.PROVIDER_AUTH),
        (429, ProviderErrorCode.PROVIDER_RATE_LIMITED),
        (400, ProviderErrorCode.PROVIDER_ERROR),
    ],
)
def test_client_error_statuses_map(status: int, expected: ProviderErrorCode) -> None:
    client = _client_raising(ClientError(status, {"error": {"message": "x"}}))
    with pytest.raises(ProviderError) as raised:
        client.generate(_request())
    assert raised.value.code == expected


def test_server_error_maps_to_unavailable() -> None:
    client = _client_raising(ServerError(500, {"error": {"message": "x"}}))
    with pytest.raises(ProviderError) as raised:
        client.generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_UNAVAILABLE


def test_safety_finish_reason_maps_to_refused() -> None:
    response = _response(
        text=None,
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.SAFETY)],
    )
    with pytest.raises(ProviderError) as raised:
        _client_returning(response).generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_REFUSED


def test_prompt_block_maps_to_refused() -> None:
    response = _response(
        prompt_feedback=SimpleNamespace(block_reason="SAFETY"),
        candidates=[],
        text=None,
    )
    with pytest.raises(ProviderError) as raised:
        _client_returning(response).generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_REFUSED


def test_empty_text_maps_to_response_invalid() -> None:
    response = _response(text=None, candidates=[SimpleNamespace(finish_reason="STOP")])
    with pytest.raises(ProviderError) as raised:
        _client_returning(response).generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_RESPONSE_INVALID


def test_max_tokens_maps_to_response_invalid() -> None:
    response = _response(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)]
    )
    with pytest.raises(ProviderError) as raised:
        _client_returning(response).generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_RESPONSE_INVALID


def test_text_property_raising_maps_to_response_invalid() -> None:
    class ExplodingText:
        prompt_feedback = None
        candidates = [SimpleNamespace(finish_reason="STOP")]
        usage_metadata = None

        @property
        def text(self):
            raise ValueError("no text parts")

    with pytest.raises(ProviderError) as raised:
        _client_returning(ExplodingText()).generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_RESPONSE_INVALID


def test_transport_error_maps_to_unavailable() -> None:
    client = _client_raising(httpx.ConnectError("refused"))
    with pytest.raises(ProviderError) as raised:
        client.generate(_request())
    assert raised.value.code == ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert raised.value.transient


def test_requires_api_key() -> None:
    with pytest.raises(ValueError):
        GeminiTextClient("", config())
