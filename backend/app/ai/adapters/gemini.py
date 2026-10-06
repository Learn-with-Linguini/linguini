"""Gemini ``generate_content`` adapters for the text and vision contracts.

Both adapters share one call path and differ only in the content they send.
Provider response text is never surfaced in errors or logs.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.ai.adapters.common import (
    parse_retry_after,
    payload_error,
    provider_error,
    status_message,
)
from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.metadata import FinishStatus, ResponseMetadata, TokenUsage
from app.ai.contracts.text import TextModelRequest, TextModelResponse
from app.ai.contracts.vision import VisionModelRequest, VisionModelResponse

GEMINI_PROVIDER = "gemini"
GEMINI_ENDPOINT = "gemini.generate_content"

_REFUSAL_FINISH_REASONS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.SPII,
        types.FinishReason.IMAGE_SAFETY,
        types.FinishReason.IMAGE_PROHIBITED_CONTENT,
    }
)

_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"


def _reason_name(reason: Any) -> str | None:
    if reason is None:
        return None
    return getattr(reason, "name", None) or str(reason)


def _finish_status(reason: str | None) -> FinishStatus:
    if reason == "STOP":
        return FinishStatus.COMPLETED
    if reason == "MAX_TOKENS":
        return FinishStatus.MAX_TOKENS
    if reason in {member.name for member in _REFUSAL_FINISH_REASONS}:
        return FinishStatus.CONTENT_FILTER
    return FinishStatus.OTHER


def _retry_info_seconds(details: Any) -> float | None:
    """The ``retryDelay`` of a google.rpc.RetryInfo detail, such as ``"17s"``."""
    error = details.get("error", details) if isinstance(details, dict) else None
    if not isinstance(error, dict):
        return None
    for item in error.get("details") or []:
        if not isinstance(item, dict) or item.get("@type") != _RETRY_INFO_TYPE:
            continue
        delay = item.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return max(0.0, float(delay[:-1]))
            except ValueError:
                return None
    return None


# One HTTP attempt per call. google-genai retries only when retry options are
# set; pinning a single attempt keeps every outbound call visible to the
# router's call budget instead of hidden inside the SDK.
NO_SDK_RETRIES = types.HttpRetryOptions(attempts=1)


def _gemini_json_schema(value: Any) -> Any:
    """Avoid nested array bounds that exceed Gemini's schema complexity budget.

    The original contract remains unchanged; Pydantic enforces array limits
    on the generated output rather than Gemini's schema compiler.
    """
    if isinstance(value, dict):
        return {key: _gemini_json_schema(item) for key, item in value.items() if key != "maxItems"}
    if isinstance(value, list):
        return [_gemini_json_schema(item) for item in value]
    return value


class GeminiClient:
    """Calls ``models.generate_content`` with a JSON-schema response."""

    KIND = "text"

    def __init__(
        self,
        api_key: str,
        config: ModelConfig,
        *,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._config = config
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(config.timeout_seconds * 1_000),
                retry_options=NO_SDK_RETRIES,
            ),
        )

    @property
    def _label(self) -> str:
        return "provider" if self.KIND == "text" else f"{self.KIND} provider"

    def _error(
        self,
        code: ProviderErrorCode,
        message: str,
        prompt_version: str,
        start: float,
        **details: Any,
    ) -> ProviderError:
        return provider_error(
            code,
            message,
            kind=self.KIND,
            provider=GEMINI_PROVIDER,
            endpoint=GEMINI_ENDPOINT,
            model=self._config.model_name,
            prompt_version=prompt_version,
            start=start,
            **details,
        )

    def _api_error(self, error: APIError, version: str, start: float) -> ProviderError:
        status_code = getattr(error, "code", None)
        code, scope = payload_error(status_code, getattr(error, "details", None))
        retry_after = parse_retry_after(getattr(getattr(error, "response", None), "headers", None))
        if retry_after is None:
            retry_after = _retry_info_seconds(getattr(error, "details", None))
        return self._error(
            code,
            status_message(self._label, code),
            version,
            start,
            status_code=status_code,
            retry_after_seconds=retry_after,
            scope=scope,
        )

    def _send(
        self,
        request: TextModelRequest | VisionModelRequest,
        contents: list[Any],
        timeout_seconds: float | None = None,
    ) -> tuple[str, ResponseMetadata]:
        start = time.monotonic()
        version = request.prompt_version
        # Gemini 3.5 Flash-Lite and later reject sampling overrides.
        model_version = re.match(r"(?:models/)?gemini-(\d+)\.(\d+)", self._config.model_name)
        sampling = {"temperature": self._config.temperature}
        if model_version and tuple(map(int, model_version.groups())) >= (3, 5):
            sampling = {}
        try:
            response = self._client.models.generate_content(
                model=self._config.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=request.system_prompt,
                    **sampling,
                    response_mime_type="application/json",
                    response_json_schema=_gemini_json_schema(request.json_schema),
                    max_output_tokens=self._config.max_output_tokens,
                    http_options=(
                        None
                        if timeout_seconds is None
                        else types.HttpOptions(timeout=max(1, int(timeout_seconds * 1_000)))
                    ),
                ),
            )
        except (httpx.TimeoutException, TimeoutError):
            raise self._error(
                ProviderErrorCode.PROVIDER_TIMEOUT,
                f"{self._label} timed out",
                version,
                start,
            ) from None
        except APIError as error:
            raise self._api_error(error, version, start) from None
        except Exception as error:
            code = (
                ProviderErrorCode.PROVIDER_UNAVAILABLE
                if isinstance(error, httpx.HTTPError)
                else ProviderErrorCode.PROVIDER_ERROR
            )
            raise self._error(
                code,
                status_message(self._label, code),
                version,
                start,
                scope=ProviderFailureScope.SERVICE,
            ) from None

        return self._parse_response(response, version, start)

    def _parse_response(
        self, response: Any, version: str, start: float
    ) -> tuple[str, ResponseMetadata]:
        # ``response.text`` is a property in google-genai that raises when the
        # candidate list is blocked/empty or contains non-text parts.
        try:
            prompt_feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(prompt_feedback, "block_reason", None)
            candidates = getattr(response, "candidates", None) or []
            finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
            if block_reason or finish_reason in _REFUSAL_FINISH_REASONS:
                raise self._error(
                    ProviderErrorCode.PROVIDER_REFUSED,
                    f"{self._label} refused the request",
                    version,
                    start,
                )
            output_text = getattr(response, "text", None) or ""
            usage = getattr(response, "usage_metadata", None)
            reported_model = getattr(response, "model_version", None)
            response_id = getattr(response, "response_id", None)
            reason = _reason_name(finish_reason)
            metadata = ResponseMetadata(
                provider=GEMINI_PROVIDER,
                endpoint=GEMINI_ENDPOINT,
                requested_model=self._config.model_name,
                model=reported_model if isinstance(reported_model, str) else None,
                request_id=response_id if isinstance(response_id, str) else None,
                finish_status=_finish_status(reason),
                finish_reason=reason,
                usage=TokenUsage(
                    input_tokens=getattr(usage, "prompt_token_count", None),
                    output_tokens=getattr(usage, "candidates_token_count", None),
                    total_tokens=getattr(usage, "total_token_count", None),
                ),
            )
        except ProviderError:
            raise
        except Exception:
            raise self._error(
                ProviderErrorCode.PROVIDER_RESPONSE_INVALID,
                f"{self._label} returned incomplete output",
                version,
                start,
            ) from None

        if block_reason or finish_reason in _REFUSAL_FINISH_REASONS:
            raise self._error(
                ProviderErrorCode.PROVIDER_REFUSED,
                f"{self._label} refused the request",
                version,
                start,
            )

        if (
            not isinstance(output_text, str)
            or not output_text.strip()
            or _reason_name(finish_reason) == "MAX_TOKENS"
        ):
            raise self._error(
                ProviderErrorCode.PROVIDER_RESPONSE_INVALID,
                f"{self._label} returned incomplete output",
                version,
                start,
            )

        return output_text, metadata


class GeminiTextClient(GeminiClient):
    KIND = "text"

    def generate(
        self, request: TextModelRequest, *, timeout_seconds: float | None = None
    ) -> TextModelResponse:
        text, metadata = self._send(request, [request.user_content], timeout_seconds)
        return TextModelResponse(
            output_text=text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=metadata.usage.input_tokens,
            output_tokens=metadata.usage.output_tokens,
            metadata=metadata,
        )


class GeminiVisionClient(GeminiClient):
    KIND = "vision"

    def generate(
        self, request: VisionModelRequest, *, timeout_seconds: float | None = None
    ) -> VisionModelResponse:
        text, metadata = self._send(
            request,
            [
                request.user_instruction,
                types.Part.from_bytes(
                    data=request.image.data,
                    mime_type=request.image.mime_type,
                ),
            ],
            timeout_seconds,
        )
        return VisionModelResponse(
            output_text=text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=metadata.usage.input_tokens,
            output_tokens=metadata.usage.output_tokens,
            metadata=metadata,
        )
