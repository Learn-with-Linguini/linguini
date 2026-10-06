"""OpenRouter adapters for the text and vision contracts.

OpenRouter serves many vendors (Anthropic, Qwen, DeepSeek, Meta, Mistral, and
OpenAI's and Google's own models) behind an OpenAI-compatible Responses API,
including strict JSON-schema structured output and the same ``usage`` shape.
Models are named ``vendor/model`` (for example ``anthropic/claude-haiku-4.5``),
and the response reports the model that actually served the call.

Calls are billed to the OpenRouter account and routed to whichever host
OpenRouter picks, so latency includes its routing hop. Its statuses differ
from OpenAI's: 402 means the account is out of credits and 403 means the
input was flagged by moderation, not that the key was rejected.

Upstream fallback is always sent explicitly: ``provider.allow_fallbacks``
lets OpenRouter retry the same model on another host, and ``models`` lists
fallback models in priority order. Those internal attempts happen inside one
HTTP request, so Linguini's outbound-call budget counts them as one call and
cannot see or limit them.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.adapters.responses_api import (
    ResponsesEndpoint,
    ResponsesTextClient,
    ResponsesVisionClient,
)
from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderFailureScope
from app.ai.contracts.text import TextModelRequest
from app.ai.contracts.vision import VisionModelRequest

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_RESPONSES = ResponsesEndpoint(
    provider="openrouter",
    name="openrouter.responses",
    base_url=OPENROUTER_BASE_URL,
    status_scopes={
        402: ProviderFailureScope.QUOTA,
        403: ProviderFailureScope.REQUEST,
    },
)


class _OpenRouterClient:
    ENDPOINT = OPENROUTER_RESPONSES

    def __init__(
        self,
        api_key: str,
        config: ModelConfig,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        *,
        allow_fallbacks: bool = True,
        fallback_models: tuple[str, ...] = (),
    ) -> None:
        super().__init__(api_key, config, base_url, client)
        self._allow_fallbacks = allow_fallbacks
        self._fallback_models = tuple(fallback_models)

    def _request_body(
        self, request: TextModelRequest | VisionModelRequest, user_content: list[dict]
    ) -> dict[str, Any]:
        body = super()._request_body(request, user_content)
        body["provider"] = {"allow_fallbacks": self._allow_fallbacks}
        if self._fallback_models:
            body["models"] = list(self._fallback_models)
        return body


class OpenRouterTextClient(_OpenRouterClient, ResponsesTextClient):
    pass


class OpenRouterVisionClient(_OpenRouterClient, ResponsesVisionClient):
    pass
