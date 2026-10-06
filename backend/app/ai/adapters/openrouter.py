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
"""

from __future__ import annotations

from app.ai.adapters.responses_api import (
    ResponsesEndpoint,
    ResponsesTextClient,
    ResponsesVisionClient,
)
from app.ai.contracts.errors import ProviderFailureScope

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


class OpenRouterTextClient(ResponsesTextClient):
    ENDPOINT = OPENROUTER_RESPONSES


class OpenRouterVisionClient(ResponsesVisionClient):
    ENDPOINT = OPENROUTER_RESPONSES
