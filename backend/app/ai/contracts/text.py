"""Provider-independent text-model client interface.

Every text adapter implements ``TextModelClient``. Adapters raise
``ProviderError`` and contain no feature business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.ai.contracts.config import ModelConfig
from app.ai.contracts.metadata import ResponseMetadata, RouteInfo

TextModelConfig = ModelConfig


@dataclass(frozen=True)
class TextModelRequest:
    system_prompt: str
    user_content: str
    json_schema_name: str
    json_schema: dict[str, Any]
    prompt_version: str


@dataclass(frozen=True)
class TextModelResponse:
    output_text: str
    model_name: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: ResponseMetadata | None = None
    route: RouteInfo | None = None


class TextModelClient(Protocol):
    def generate(self, request: TextModelRequest) -> TextModelResponse: ...
