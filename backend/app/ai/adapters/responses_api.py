"""Shared transport for OpenAI-compatible Responses API hosts.

Hosts that speak the Responses API are compatible, not identical. Each
``ResponsesEndpoint`` states which options it is sent, where its request ID
lives and what its HTTP statuses mean, so adapters never assume one host
behaves like another.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.ai.adapters.common import (
    parse_retry_after,
    payload_error,
    provider_error,
    status_message,
)
from app.ai.adapters.deadline import CallDeadline
from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.metadata import FinishStatus, ResponseMetadata, TokenUsage
from app.ai.contracts.text import TextModelRequest, TextModelResponse
from app.ai.contracts.vision import VisionModelRequest, VisionModelResponse
from app.ai.routing.invocation import InvocationContext


@dataclass(frozen=True)
class ResponsesEndpoint:
    provider: str
    name: str
    base_url: str
    sends_temperature: bool = True
    strict_json_schema: bool = True
    request_id_headers: tuple[str, ...] = ()
    """Headers holding the request ID; the response body ``id`` is the fallback."""
    status_scopes: Mapping[int, ProviderFailureScope] = field(default_factory=dict)
    """Host-specific failure scopes that override the shared status mapping."""
    quota_exhausted_codes: frozenset[str] = frozenset()
    """429 body error codes meaning credits are exhausted, not a rate limit."""


_FINISH_REASONS = {
    "max_output_tokens": FinishStatus.MAX_TOKENS,
    "content_filter": FinishStatus.CONTENT_FILTER,
}


class ResponsesApiClient:
    """Posts one structured-output request to a Responses API endpoint.

    Makes exactly one HTTP request per ``generate`` call: ``httpx`` never
    retries, so every attempt is counted by the router's call budget.
    """

    ENDPOINT: ResponsesEndpoint
    KIND = "text"
    DEADLINE_AWARE = True

    def __init__(
        self,
        api_key: str,
        config: ModelConfig,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._config = config
        self._base_url = (base_url or self.ENDPOINT.base_url).rstrip("/")
        self._client = client

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
            provider=self.ENDPOINT.provider,
            endpoint=self.ENDPOINT.name,
            model=self._config.model_name,
            prompt_version=prompt_version,
            start=start,
            **details,
        )

    def _request_body(
        self, request: TextModelRequest | VisionModelRequest, user_content: list[dict]
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self._config.model_name}
        if self.ENDPOINT.sends_temperature:
            body["temperature"] = self._config.temperature
        body["max_output_tokens"] = self._config.max_output_tokens
        body["input"] = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": request.system_prompt}],
            },
            {"role": "user", "content": user_content},
        ]
        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": request.json_schema_name,
                "schema": request.json_schema,
                "strict": self.ENDPOINT.strict_json_schema,
            }
        }
        return body

    def _send(
        self,
        request: TextModelRequest | VisionModelRequest,
        user_content: list[dict],
        timeout_seconds: float | None = None,
        invocation: InvocationContext | None = None,
    ) -> tuple[str, ResponseMetadata]:
        start = time.monotonic()
        version = request.prompt_version
        deadline = CallDeadline(
            min(self._config.timeout_seconds, timeout_seconds)
            if timeout_seconds is not None
            else self._config.timeout_seconds,
            invocation,
        )

        async def post(client: httpx.AsyncClient) -> httpx.Response:
            body = self._request_body(request, user_content)
            return await client.post(
                f"{self._base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=deadline.begin_io(),
            )

        async def send() -> httpx.Response:
            if self._client is not None:
                return await post(self._client)
            # Per-call ownership keeps pools on this call's event loop and
            # closes sockets before cancellation returns to routing.
            async with httpx.AsyncClient() as client:
                return await post(client)

        try:
            response = deadline.run(send)
        except (httpx.TimeoutException, TimeoutError):
            raise self._error(
                ProviderErrorCode.PROVIDER_TIMEOUT,
                f"{self._label} timed out",
                version,
                start,
            ) from None
        except httpx.HTTPError:
            raise self._error(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                f"{self._label} request failed",
                version,
                start,
            ) from None

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = None
            code, scope = self._payload_error(response.status_code, body)
            raise self._error(
                code,
                status_message(self._label, code),
                version,
                start,
                status_code=response.status_code,
                retry_after_seconds=parse_retry_after(response.headers),
                scope=scope,
            )

        result = self._parse_response(response, version, start)
        try:
            deadline.check()
        except TimeoutError:
            raise self._error(
                ProviderErrorCode.PROVIDER_TIMEOUT, f"{self._label} timed out", version, start
            ) from None
        return result

    def _payload_error(
        self, status: int | None, body: Any
    ) -> tuple[ProviderErrorCode, ProviderFailureScope]:
        return payload_error(
            status,
            body,
            quota_exhausted_codes=self.ENDPOINT.quota_exhausted_codes,
            fallback_scope=self.ENDPOINT.status_scopes.get(status),
        )

    def _parse_response(
        self, response: httpx.Response, version: str, start: float
    ) -> tuple[str, ResponseMetadata]:
        try:
            body = response.json()
        except ValueError:
            raise self._error(
                ProviderErrorCode.PROVIDER_RESPONSE_INVALID,
                f"{self._label} returned a non-JSON response",
                version,
                start,
                status_code=response.status_code,
            ) from None

        if isinstance(body, dict) and (body.get("status") == "failed" or body.get("error")):
            error = body.get("error")
            embedded_status = error.get("code") if isinstance(error, dict) else None
            code, scope = self._payload_error(
                embedded_status if type(embedded_status) is int else None, body
            )
            raise self._error(
                code,
                status_message(self._label, code),
                version,
                start,
                status_code=response.status_code,
                scope=scope,
                retry_after_seconds=parse_retry_after(response.headers),
            )

        try:
            if not isinstance(body, dict):
                raise ValueError("response must be an object")
            # Find refusals before parsing optional text or metadata.
            if self._is_refusal(body):
                raise self._error(
                    ProviderErrorCode.PROVIDER_REFUSED,
                    f"{self._label} refused the request",
                    version,
                    start,
                    status_code=response.status_code,
                )
            outputs = body.get("output")
            if outputs is not None and not isinstance(outputs, list):
                raise ValueError("invalid output list")
            for output in outputs or []:
                if not isinstance(output, dict):
                    raise ValueError("invalid output item")
                content = output.get("content")
                if content is not None and not isinstance(content, list):
                    raise ValueError("invalid content list")
                if any(not isinstance(part, dict) for part in content or []):
                    raise ValueError("invalid content item")
            output_text = self._extract_text(body)
            incomplete_reason = self._incomplete_reason(body)
            if not output_text.strip() or incomplete_reason == "max_output_tokens":
                raise ValueError("incomplete output")
            return output_text, self._metadata(response, body, incomplete_reason)
        except (AttributeError, TypeError, ValueError, KeyError):
            raise self._error(
                ProviderErrorCode.PROVIDER_RESPONSE_INVALID,
                f"{self._label} returned invalid output",
                version,
                start,
                status_code=response.status_code,
            ) from None

    def _metadata(
        self, response: httpx.Response, body: dict[str, Any], incomplete_reason: str | None
    ) -> ResponseMetadata:
        usage = body.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("invalid usage")
        usage = usage or {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            count = usage.get(key)
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError("invalid token count")
        status = body.get("status")
        request_id = next(
            (
                response.headers[header]
                for header in self.ENDPOINT.request_id_headers
                if response.headers.get(header)
            ),
            None,
        )
        if request_id is None and isinstance(body.get("id"), str):
            request_id = body["id"]
        if status == "completed":
            finish_status = FinishStatus.COMPLETED
        else:
            finish_status = _FINISH_REASONS.get(incomplete_reason, FinishStatus.OTHER)
        reported_model = body.get("model")
        return ResponseMetadata(
            provider=self.ENDPOINT.provider,
            endpoint=self.ENDPOINT.name,
            requested_model=self._config.model_name,
            model=reported_model if isinstance(reported_model, str) else None,
            request_id=request_id,
            finish_status=finish_status,
            finish_reason=incomplete_reason or (status if isinstance(status, str) else None),
            usage=TokenUsage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
        )

    @staticmethod
    def _incomplete_reason(body: dict[str, Any]) -> str | None:
        if body.get("status") != "incomplete":
            return None
        details = body.get("incomplete_details") or {}
        if not isinstance(details, dict):
            raise ValueError("invalid incomplete details")
        reason = details.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("invalid incomplete reason")
        return reason

    def _is_refusal(self, body: dict[str, Any]) -> bool:
        details = body.get("incomplete_details")
        if (
            body.get("status") == "incomplete"
            and isinstance(details, dict)
            and details.get("reason") == "content_filter"
        ):
            return True
        outputs = body.get("output")
        for output in outputs if isinstance(outputs, list) else []:
            if not isinstance(output, dict):
                continue
            contents = output.get("content")
            for content in contents if isinstance(contents, list) else []:
                if isinstance(content, dict) and content.get("type") == "refusal":
                    return True
        return False

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        parts = []
        for output in body.get("output") or []:
            for content in output.get("content") or []:
                if content.get("type") == "output_text":
                    if not isinstance(content.get("text"), str):
                        raise ValueError("invalid text")
                    parts.append(content["text"])
        text = "".join(parts)
        if not text and isinstance(body.get("output_text"), str):
            text = body["output_text"]
        return text


class ResponsesTextClient(ResponsesApiClient):
    KIND = "text"

    def generate(
        self,
        request: TextModelRequest,
        *,
        timeout_seconds: float | None = None,
        invocation: InvocationContext | None = None,
    ) -> TextModelResponse:
        text, metadata = self._send(
            request,
            [{"type": "input_text", "text": request.user_content}],
            timeout_seconds,
            invocation,
        )
        return TextModelResponse(
            output_text=text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=metadata.usage.input_tokens,
            output_tokens=metadata.usage.output_tokens,
            metadata=metadata,
        )


class ResponsesVisionClient(ResponsesApiClient):
    KIND = "vision"

    def generate(
        self,
        request: VisionModelRequest,
        *,
        timeout_seconds: float | None = None,
        invocation: InvocationContext | None = None,
    ) -> VisionModelResponse:
        image_data = base64.b64encode(request.image.data).decode("ascii")
        text, metadata = self._send(
            request,
            [
                {"type": "input_text", "text": request.user_instruction},
                {
                    "type": "input_image",
                    "image_url": f"data:{request.image.mime_type};base64,{image_data}",
                },
            ],
            timeout_seconds,
            invocation,
        )
        return VisionModelResponse(
            output_text=text,
            model_name=self._config.model_name,
            prompt_version=request.prompt_version,
            input_tokens=metadata.usage.input_tokens,
            output_tokens=metadata.usage.output_tokens,
            metadata=metadata,
        )
