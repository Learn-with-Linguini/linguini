"""Provider-independent text-model client interface.

Defines the request/response contract every text adapter implements. Adapters
raise ``ProviderError`` (from ``app/ai/model_errors.py``) and contain no
feature business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TextModelConfig:
    model_name: str
    timeout_seconds: float = 30.0
    max_output_tokens: int = 1500
    max_retries: int = 1
    # Sampling temperature. Zero keeps structured extraction repeatable;
    # a higher value is only useful where variety is wanted, such as clues.
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.model_name:
            raise ValueError("model_name must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if not 0 <= self.max_retries <= 1:
            raise ValueError("max_retries must be 0 or 1: retry at most once")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")


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


class TextModelClient(Protocol):
    def generate(self, request: TextModelRequest) -> TextModelResponse: ...
