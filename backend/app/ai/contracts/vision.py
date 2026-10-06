"""Provider-independent vision-model client interface.

Images are always inlined as raw bytes; no code path accepts a remote image
URL. Adapters raise ``ProviderError`` and contain no feature business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.metadata import ResponseMetadata
from app.schemas.media import MAX_IMAGE_BYTES

ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

VisionModelConfig = ModelConfig


@dataclass(frozen=True)
class VisionImage:
    data: bytes
    mime_type: str

    def __post_init__(self) -> None:
        if self.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise ProviderError(
                ProviderErrorCode.INVALID_IMAGE,
                f"unsupported image mime type {self.mime_type!r}",
            )
        if not self.data:
            raise ProviderError(
                ProviderErrorCode.INVALID_IMAGE, "image data must not be empty"
            )
        if len(self.data) > MAX_IMAGE_BYTES:
            raise ProviderError(
                ProviderErrorCode.INVALID_IMAGE,
                f"image data exceeds the {MAX_IMAGE_BYTES}-byte limit",
            )


@dataclass(frozen=True)
class VisionModelRequest:
    image: VisionImage
    system_prompt: str
    user_instruction: str
    json_schema_name: str
    json_schema: dict[str, Any]
    prompt_version: str


@dataclass(frozen=True)
class VisionModelResponse:
    output_text: str
    model_name: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: ResponseMetadata | None = None


class VisionModelClient(Protocol):
    def generate(self, request: VisionModelRequest) -> VisionModelResponse: ...
