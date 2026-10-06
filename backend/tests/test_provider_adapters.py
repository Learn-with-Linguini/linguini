"""Normalized response metadata and provider errors across the adapters."""

import json
import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.ai.adapters.common import parse_retry_after
from app.ai.adapters.gemini import GeminiTextClient, GeminiVisionClient
from app.ai.adapters.openai import OpenAITextClient, OpenAIVisionClient
from app.ai.adapters.openrouter import OPENROUTER_BASE_URL, OpenRouterTextClient
from app.ai.adapters.responses_api import ResponsesEndpoint, ResponsesTextClient
from app.ai.contracts import (
    FinishStatus,
    ProviderError,
    ProviderErrorCode,
    ProviderFailureScope,
    TextModelConfig,
    TextModelRequest,
    VisionImage,
    VisionModelConfig,
    VisionModelRequest,
)

Code = ProviderErrorCode
Scope = ProviderFailureScope
SECRET_KEY = "sk-secret-123"
OUTPUT = json.dumps({"ok": True})
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def text_request() -> TextModelRequest:
    return TextModelRequest(
        system_prompt="sys",
        user_content="hello",
        json_schema_name="s",
        json_schema={"type": "object"},
        prompt_version="v1",
    )


def vision_request() -> VisionModelRequest:
    return VisionModelRequest(
        image=VisionImage(PNG, "image/png"),
        system_prompt="sys",
        user_instruction="look",
        json_schema_name="s",
        json_schema={"type": "object"},
        prompt_version="v1",
    )


def responses_body(**overrides):
    body = {
        "id": "resp_abc",
        "model": "gpt-4.1-mini-2025-04-14",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": OUTPUT}]}],
        "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    }
    body.update(overrides)
    return body


def http_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def responses_adapter(cls, handler, **kwargs):
    config = TextModelConfig(model_name="gpt-4.1-mini")
    return cls(SECRET_KEY, config, client=http_client(handler), **kwargs)


def test_openai_metadata_reports_actual_model_request_id_and_usage():
    def handler(request):
        return httpx.Response(200, json=responses_body(), headers={"x-request-id": "req_123"})

    response = responses_adapter(OpenAITextClient, handler).generate(text_request())

    assert response.model_name == "gpt-4.1-mini"
    assert (response.input_tokens, response.output_tokens) == (11, 7)
    meta = response.metadata
    assert meta.provider == "openai"
    assert meta.endpoint == "openai.responses"
    assert meta.requested_model == "gpt-4.1-mini"
    assert meta.model == "gpt-4.1-mini-2025-04-14"
    assert meta.request_id == "req_123"
    assert meta.finish_status is FinishStatus.COMPLETED
    assert meta.finish_reason == "completed"
    usage = meta.usage
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (11, 7, 18)


def test_missing_usage_and_model_stay_unknown():
    body = responses_body(usage=None, model=None, status="incomplete",
                          incomplete_details={"reason": "other"})
    del body["id"]

    def handler(request):
        return httpx.Response(200, json=body)

    meta = responses_adapter(OpenAITextClient, handler).generate(text_request()).metadata

    assert meta.model is None
    assert meta.request_id is None
    assert meta.finish_status is FinishStatus.OTHER
    assert meta.finish_reason == "other"
    assert meta.usage.input_tokens is None and meta.usage.total_tokens is None


def test_openrouter_uses_its_own_host_and_reports_the_routed_model():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=responses_body(id="gen-42", model="anthropic/claude-haiku-4.5")
        )

    client = OpenRouterTextClient(
        SECRET_KEY,
        TextModelConfig(model_name="anthropic/claude-haiku-4.5"),
        client=http_client(handler),
    )
    meta = client.generate(text_request()).metadata

    assert seen["url"] == f"{OPENROUTER_BASE_URL}/responses"
    assert seen["body"]["text"]["format"]["strict"] is True
    assert meta.provider == "openrouter"
    assert meta.endpoint == "openrouter.responses"
    assert meta.request_id == "gen-42"
    assert meta.model == "anthropic/claude-haiku-4.5"


def test_endpoint_options_are_explicit():
    endpoint = ResponsesEndpoint(
        provider="custom",
        name="custom.responses",
        base_url="https://example.test/v1",
        sends_temperature=False,
        strict_json_schema=False,
    )

    class CustomClient(ResponsesTextClient):
        ENDPOINT = endpoint

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=responses_body())

    responses_adapter(CustomClient, handler).generate(text_request())

    assert "temperature" not in seen["body"]
    assert seen["body"]["text"]["format"]["strict"] is False


@pytest.mark.parametrize(
    ("cls", "status", "code", "scope"),
    [
        (OpenAITextClient, 401, Code.PROVIDER_AUTH, Scope.CREDENTIALS),
        (OpenAITextClient, 403, Code.PROVIDER_AUTH, Scope.CREDENTIALS),
        (OpenAITextClient, 404, Code.PROVIDER_ERROR, Scope.MODEL),
        (OpenAITextClient, 400, Code.PROVIDER_ERROR, Scope.REQUEST),
        (OpenAITextClient, 503, Code.PROVIDER_UNAVAILABLE, Scope.SERVICE),
        (OpenRouterTextClient, 402, Code.PROVIDER_ERROR, Scope.QUOTA),
        (OpenRouterTextClient, 403, Code.PROVIDER_AUTH, Scope.REQUEST),
        (OpenRouterTextClient, 401, Code.PROVIDER_AUTH, Scope.CREDENTIALS),
    ],
)
def test_http_errors_carry_status_and_provider_scope(cls, status, code, scope):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": f"bad key {SECRET_KEY}"}})

    with pytest.raises(ProviderError) as raised:
        responses_adapter(cls, handler).generate(text_request())

    error = raised.value
    assert error.code is code
    assert error.scope is scope
    assert error.status_code == status
    assert error.provider == cls.ENDPOINT.provider
    assert SECRET_KEY not in str(error)
    assert SECRET_KEY not in repr(error.args)


def test_rate_limit_reports_retry_after_without_leaking_secrets(caplog):
    def handler(request):
        return httpx.Response(
            429, headers={"Retry-After": "12"}, json={"error": {"message": SECRET_KEY}}
        )

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError) as raised:
        responses_adapter(OpenAIVisionClient, handler).generate(vision_request())

    error = raised.value
    assert error.code is Code.PROVIDER_RATE_LIMITED
    assert error.transient
    assert error.scope is Scope.QUOTA
    assert error.retry_after_seconds == 12
    assert str(error) == "vision provider rate limited"
    record = caplog.records[-1]
    assert record.retry_after_seconds == 12
    assert record.scope == "quota"
    assert SECRET_KEY not in caplog.text
    assert all(SECRET_KEY not in str(value) for value in vars(record).values())


def test_transport_failures_are_service_scoped():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(ProviderError) as raised:
        responses_adapter(OpenAITextClient, handler).generate(text_request())

    assert raised.value.code is Code.PROVIDER_TIMEOUT
    assert raised.value.scope is Scope.SERVICE
    assert raised.value.status_code is None


def test_parse_retry_after_variants():
    future = datetime.now(UTC) + timedelta(seconds=30)
    assert parse_retry_after(httpx.Headers({"retry-after-ms": "1500"})) == 1.5
    assert parse_retry_after({"Retry-After": "3"}) == 3
    assert 25 <= parse_retry_after({"Retry-After": format_datetime(future, usegmt=True)}) <= 30
    assert parse_retry_after({"Retry-After": "-4"}) == 0
    assert parse_retry_after({"Retry-After": "soon"}) is None
    assert parse_retry_after({"Retry-After": "inf"}) is None
    assert parse_retry_after(None) is None


def gemini(cls, *, response=None, error=None):
    class Models:
        def generate_content(self, **kwargs):
            if error is not None:
                raise error
            return response

    return cls(SECRET_KEY, TextModelConfig(model_name="gemini-flash"),
               client=SimpleNamespace(models=Models()))


def gemini_response(**overrides):
    values = {
        "text": OUTPUT,
        "prompt_feedback": None,
        "candidates": [SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        "usage_metadata": SimpleNamespace(
            prompt_token_count=5, candidates_token_count=3, total_token_count=9
        ),
        "model_version": "gemini-flash-001",
        "response_id": "gem-resp-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_gemini_metadata_reports_model_version_response_id_and_usage():
    response = gemini(GeminiTextClient, response=gemini_response()).generate(text_request())

    meta = response.metadata
    assert (response.input_tokens, response.output_tokens) == (5, 3)
    assert meta.provider == "gemini"
    assert meta.endpoint == "gemini.generate_content"
    assert meta.requested_model == "gemini-flash"
    assert meta.model == "gemini-flash-001"
    assert meta.request_id == "gem-resp-1"
    assert meta.finish_status is FinishStatus.COMPLETED
    assert meta.finish_reason == "STOP"
    assert meta.usage.total_tokens == 9


def test_gemini_vision_reports_metadata_and_tolerates_missing_fields():
    response = gemini(
        GeminiVisionClient,
        response=SimpleNamespace(
            text=OUTPUT,
            prompt_feedback=None,
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=None,
        ),
    ).generate(vision_request())

    meta = response.metadata
    assert meta.model is None and meta.request_id is None
    assert meta.finish_status is FinishStatus.COMPLETED
    assert meta.usage.input_tokens is None


def test_gemini_rate_limit_reads_retry_info():
    error = ClientError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": SECRET_KEY,
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}
                ],
            }
        },
    )

    with pytest.raises(ProviderError) as raised:
        gemini(GeminiTextClient, error=error).generate(text_request())

    assert raised.value.code is Code.PROVIDER_RATE_LIMITED
    assert raised.value.retry_after_seconds == 17
    assert raised.value.scope is Scope.QUOTA
    assert raised.value.provider == "gemini"
    assert SECRET_KEY not in str(raised.value)


@pytest.mark.parametrize(
    ("status", "rpc_status", "code", "scope"),
    [
        (400, "FAILED_PRECONDITION", Code.PROVIDER_ERROR, Scope.QUOTA),
        (404, "NOT_FOUND", Code.PROVIDER_ERROR, Scope.MODEL),
        (400, "INVALID_ARGUMENT", Code.PROVIDER_ERROR, Scope.REQUEST),
        (403, "PERMISSION_DENIED", Code.PROVIDER_AUTH, Scope.CREDENTIALS),
    ],
)
def test_gemini_rpc_status_sets_scope(status, rpc_status, code, scope, caplog):
    error = ClientError(
        status, {"error": {"code": status, "status": rpc_status, "message": SECRET_KEY}}
    )

    with pytest.raises(ProviderError) as raised:
        gemini(GeminiVisionClient, error=error).generate(vision_request())

    assert raised.value.code is code
    assert raised.value.scope is scope
    assert raised.value.status_code == status
    assert raised.value.retry_after_seconds is None
    message = caplog.records[-1].getMessage()
    assert "vision provider error: provider=gemini model=gemini-flash" in message
    assert f"status_code={status} code={code.value} scope={scope.value}" in message
    assert SECRET_KEY not in caplog.text


def test_gemini_server_error_is_service_scoped():
    error = ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "x"}})

    with pytest.raises(ProviderError) as raised:
        gemini(GeminiTextClient, error=error).generate(text_request())

    assert raised.value.code is Code.PROVIDER_UNAVAILABLE
    assert raised.value.scope is Scope.SERVICE
    assert raised.value.transient


def test_errors_default_scope_from_code_and_keep_old_signature():
    error = ProviderError(Code.PROVIDER_REFUSED, "refused")

    assert error.scope is Scope.RESPONSE
    assert error.status_code is None and error.retry_after_seconds is None
    assert not error.transient


def test_vision_and_text_share_one_config_contract():
    assert VisionModelConfig is TextModelConfig


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (OpenAITextClient, Code.PROVIDER_ERROR),
        (OpenRouterTextClient, Code.PROVIDER_RATE_LIMITED),
    ],
)
def test_only_declared_429_codes_mean_exhausted_credits(cls, code):
    def handler(request):
        return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})

    with pytest.raises(ProviderError) as raised:
        responses_adapter(cls, handler).generate(text_request())

    assert raised.value.code is code
    assert raised.value.scope is Scope.QUOTA
    assert raised.value.status_code == 429


def test_plain_openai_429_stays_a_rate_limit():
    def handler(request):
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    with pytest.raises(ProviderError) as raised:
        responses_adapter(OpenAITextClient, handler).generate(text_request())

    assert raised.value.code is Code.PROVIDER_RATE_LIMITED
