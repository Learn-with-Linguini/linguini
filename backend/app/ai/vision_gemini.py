"""Gemini adapter for the vision-model client interface.

Turns a ``VisionModelRequest`` into a ``VisionModelResponse`` and maps provider
failures onto stable ``VisionModelError`` codes. Contains no scene-analysis
knowledge; provider response text is never surfaced in errors or logs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError

from app.services.vision_model import (
    VisionModelClient,
    VisionModelConfig,
    VisionModelError,
    VisionModelErrorCode,
    VisionModelRequest,
    VisionModelResponse,
)

logger = logging.getLogger(__name__)

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


class GeminiVisionClient(VisionModelClient):
    def __init__(
        self,
        api_key: str,
        config: VisionModelConfig,
        *,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._config = config
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(config.timeout_seconds * 1_000)
            ),
        )

    def generate(self, request: VisionModelRequest) -> VisionModelResponse:
        start = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self._config.model_name,
                contents=[
                    request.user_instruction,
                    types.Part.from_bytes(
                        data=request.image.data,
                        mime_type=request.image.mime_type,
                    ),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=request.system_prompt,
                    temperature=self._config.temperature,
                    response_mime_type="application/json",
                    response_json_schema=request.json_schema,
                    max_output_tokens=self._config.max_output_tokens,
                ),
            )
        except (httpx.TimeoutException, TimeoutError):
            self._log_error(VisionModelErrorCode.PROVIDER_TIMEOUT, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_TIMEOUT, "vision provider timed out"
            ) from None
        except ClientError as error:
            code = self._client_error_code(error)
            self._log_error(code, request, start, getattr(error, "code", None))
            raise VisionModelError(code, self._status_message(code)) from None
        except APIError as error:
            code = self._api_error_code(error)
            self._log_error(code, request, start, getattr(error, "code", None))
            raise VisionModelError(code, self._status_message(code)) from None
        except Exception as error:
            code = self._transport_error_code(error)
            self._log_error(code, request, start)
            raise VisionModelError(code, self._status_message(code)) from None

        return self._parse_response(response, request, start)

    @staticmethod
    def _status_code_error(status_code: int | None) -> VisionModelErrorCode:
        if status_code in (401, 403):
            return VisionModelErrorCode.PROVIDER_AUTH
        if status_code == 429:
            return VisionModelErrorCode.PROVIDER_RATE_LIMITED
        if status_code is not None and (status_code == 408 or status_code >= 500):
            return VisionModelErrorCode.PROVIDER_UNAVAILABLE
        return VisionModelErrorCode.PROVIDER_ERROR

    @classmethod
    def _client_error_code(cls, error: ClientError) -> VisionModelErrorCode:
        return cls._status_code_error(getattr(error, "code", None))

    @classmethod
    def _api_error_code(cls, error: APIError) -> VisionModelErrorCode:
        return cls._status_code_error(getattr(error, "code", None))

    @staticmethod
    def _transport_error_code(error: Exception) -> VisionModelErrorCode:
        if isinstance(error, httpx.HTTPError):
            return VisionModelErrorCode.PROVIDER_UNAVAILABLE
        return VisionModelErrorCode.PROVIDER_ERROR

    @staticmethod
    def _status_message(code: VisionModelErrorCode) -> str:
        return {
            VisionModelErrorCode.PROVIDER_TIMEOUT: "vision provider timed out",
            VisionModelErrorCode.PROVIDER_AUTH: "vision provider authentication failed",
            VisionModelErrorCode.PROVIDER_RATE_LIMITED: "vision provider rate limited",
            VisionModelErrorCode.PROVIDER_UNAVAILABLE: "vision provider unavailable",
        }.get(code, "vision provider request failed")

    def _parse_response(
        self,
        response: Any,
        request: VisionModelRequest,
        start: float,
    ) -> VisionModelResponse:
        # ``response.text`` is a property in google-genai that raises when the
        # candidate list is blocked/empty or contains non-text parts.
        try:
            prompt_feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(prompt_feedback, "block_reason", None)
            candidates = getattr(response, "candidates", None) or []
            finish_reason = (
                getattr(candidates[0], "finish_reason", None)
                if candidates
                else None
            )
            output_text = getattr(response, "text", None) or ""
            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
        except Exception:
            self._log_error(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID, request, start
            )
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID,
                "vision provider returned incomplete output",
            ) from None

        if block_reason:
            self._log_error(VisionModelErrorCode.PROVIDER_REFUSED, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_REFUSED,
                "vision provider refused the request",
            )

        if finish_reason in _REFUSAL_FINISH_REASONS:
            self._log_error(VisionModelErrorCode.PROVIDER_REFUSED, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_REFUSED,
                "vision provider refused the request",
            )

        if not output_text or finish_reason is types.FinishReason.MAX_TOKENS:
            self._log_error(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID, request, start
            )
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID,
                "vision provider returned incomplete output",
            )

        return VisionModelResponse(
            output_text=output_text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _log_error(
        self,
        code: VisionModelErrorCode,
        request: VisionModelRequest,
        start: float,
        status_code: int | None = None,
    ) -> None:
        logger.warning(
            "vision provider error",
            extra={
                "code": code.value,
                "status_code": status_code,
                "model": self._config.model_name,
                "prompt_version": request.prompt_version,
                "latency_seconds": round(time.monotonic() - start, 3),
            },
        )
