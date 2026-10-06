"""Normalized facts about one successful provider response."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FinishStatus(StrEnum):
    COMPLETED = "completed"
    MAX_TOKENS = "maxTokens"
    REFUSED = "refused"
    CONTENT_FILTER = "contentFilter"
    OTHER = "other"


@dataclass(frozen=True)
class TokenUsage:
    """Token counts the provider reported; ``None`` when it reported none."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ResponseMetadata:
    provider: str
    endpoint: str
    requested_model: str
    model: str | None = None
    """The model the provider reports serving, such as a dated snapshot."""
    request_id: str | None = None
    finish_status: FinishStatus = FinishStatus.OTHER
    finish_reason: str | None = None
    """The provider's own finish or status code, for diagnostics."""
    usage: TokenUsage = field(default_factory=TokenUsage)
