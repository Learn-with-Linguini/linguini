"""OpenAI adapter for the vision-model client interface.

Calls the Responses API with strict structured output; the image is inlined as
a base64 data URI. Provider response bodies are never surfaced in errors or
logs — only stable ``VisionModelErrorCode`` codes travel upward.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from app.services.vision_model import (
    VisionModelClient,
    VisionModelConfig,
    VisionModelError,
    VisionModelErrorCode,
    VisionModelRequest,
    VisionModelResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIVisionClient(VisionModelClient):
    def __init__(
        self,
        api_key: str,
        config: VisionModelConfig,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._config = config
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    def generate(self, request: VisionModelRequest) -> VisionModelResponse:
        start = time.monotonic()
        try:
            response = self._client.post(
                f"{self._base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=self._request_body(request),
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException:
            self._log_error(VisionModelErrorCode.PROVIDER_TIMEOUT, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_TIMEOUT, "vision provider timed out"
            ) from None
        except httpx.HTTPError:
            self._log_error(VisionModelErrorCode.PROVIDER_UNAVAILABLE, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_UNAVAILABLE,
                "vision provider request failed",
            ) from None

        if response.status_code >= 400:
            code = self._status_code_error(response.status_code)
            self._log_error(code, request, start, response.status_code)
            raise VisionModelError(code, self._status_message(code))

        return self._parse_response(response, request, start)

    def _request_body(self, request: VisionModelRequest) -> dict[str, Any]:
        image_data = base64.b64encode(request.image.data).decode("ascii")
        return {
            "model": self._config.model_name,
            "temperature": self._config.temperature,
            "max_output_tokens": self._config.max_output_tokens,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": request.system_prompt},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request.user_instruction},
                        {
                            "type": "input_image",
                            "image_url": (
                                f"data:{request.image.mime_type};base64,{image_data}"
                            ),
                        },
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.json_schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                }
            },
        }

    @staticmethod
    def _status_code_error(status_code: int) -> VisionModelErrorCode:
        if status_code in (401, 403):
            return VisionModelErrorCode.PROVIDER_AUTH
        if status_code == 429:
            return VisionModelErrorCode.PROVIDER_RATE_LIMITED
        if status_code == 408 or status_code >= 500:
            return VisionModelErrorCode.PROVIDER_UNAVAILABLE
        return VisionModelErrorCode.PROVIDER_ERROR

    @staticmethod
    def _status_message(code: VisionModelErrorCode) -> str:
        return {
            VisionModelErrorCode.PROVIDER_AUTH: "vision provider authentication failed",
            VisionModelErrorCode.PROVIDER_RATE_LIMITED: "vision provider rate limited",
            VisionModelErrorCode.PROVIDER_UNAVAILABLE: "vision provider unavailable",
        }.get(code, "vision provider request failed")

    def _parse_response(
        self,
        response: httpx.Response,
        request: VisionModelRequest,
        start: float,
    ) -> VisionModelResponse:
        try:
            body = response.json()
        except ValueError:
            self._log_error(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID, request, start
            )
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID,
                "vision provider returned a non-JSON response",
            ) from None

        if self._is_refusal(body):
            self._log_error(VisionModelErrorCode.PROVIDER_REFUSED, request, start)
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_REFUSED,
                "vision provider refused the request",
            )

        output_text = self._extract_text(body)
        incomplete_reason = self._incomplete_reason(body)
        if not output_text or incomplete_reason == "max_output_tokens":
            self._log_error(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID, request, start
            )
            raise VisionModelError(
                VisionModelErrorCode.PROVIDER_RESPONSE_INVALID,
                "vision provider returned incomplete output",
            )

        usage = body.get("usage") or {}
        return VisionModelResponse(
            output_text=output_text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

    @staticmethod
    def _incomplete_reason(body: dict[str, Any]) -> str | None:
        if body.get("status") != "incomplete":
            return None
        details = body.get("incomplete_details") or {}
        return details.get("reason")

    def _is_refusal(self, body: dict[str, Any]) -> bool:
        if self._incomplete_reason(body) == "content_filter":
            return True
        for output in body.get("output") or []:
            for content in output.get("content") or []:
                if content.get("type") == "refusal":
                    return True
        return False

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        parts = []
        for output in body.get("output") or []:
            for content in output.get("content") or []:
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(content["text"])
        text = "".join(parts)
        if not text and isinstance(body.get("output_text"), str):
            text = body["output_text"]
        return text

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


def build_vision_client(
    provider: str,
    api_key: str,
    config: VisionModelConfig,
    *,
    base_url: str | None = None,
    client: httpx.Client | None = None,
) -> VisionModelClient:
    """Provider seam: new providers (Gemini, etc.) plug in here."""
    if provider == "openai":
        kwargs = {} if base_url is None else {"base_url": base_url}
        return OpenAIVisionClient(api_key, config, client=client, **kwargs)
    raise ValueError(f"unknown vision provider {provider!r}")
