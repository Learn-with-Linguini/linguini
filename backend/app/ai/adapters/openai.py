"""OpenAI Responses API adapters for the text and vision contracts."""

from __future__ import annotations

from app.ai.adapters.responses_api import (
    ResponsesEndpoint,
    ResponsesTextClient,
    ResponsesVisionClient,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

OPENAI_RESPONSES = ResponsesEndpoint(
    provider="openai",
    name="openai.responses",
    base_url=DEFAULT_OPENAI_BASE_URL,
    request_id_headers=("x-request-id",),
    quota_exhausted_codes=frozenset({"insufficient_quota"}),
)


class OpenAITextClient(ResponsesTextClient):
    ENDPOINT = OPENAI_RESPONSES


class OpenAIVisionClient(ResponsesVisionClient):
    ENDPOINT = OPENAI_RESPONSES
