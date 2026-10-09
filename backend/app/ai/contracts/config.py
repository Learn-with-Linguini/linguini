"""Per-call model settings shared by text and vision adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
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
