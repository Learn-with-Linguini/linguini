"""Provider-independent vision-model client interface.

Defines the request/response contract every vision adapter implements plus the
stable error codes surfaced to callers. Images are always inlined as raw bytes
— no code path accepts a remote image URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from app.ai.model_errors import ProviderError, ProviderErrorCode
from app.schemas.media import MAX_IMAGE_BYTES

ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# Vision adapters keep the historical names; the shared definitions live in
# app/ai/model_errors.py so text adapters raise the same errors.
VisionModelErrorCode = ProviderErrorCode
VisionModelError = ProviderError


@dataclass(frozen=True)
class VisionImage:
    data: bytes
    mime_type: str

    def __post_init__(self) -> None:
        if self.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise VisionModelError(
                VisionModelErrorCode.INVALID_IMAGE,
                f"unsupported image mime type {self.mime_type!r}",
            )
        if not self.data:
            raise VisionModelError(
                VisionModelErrorCode.INVALID_IMAGE, "image data must not be empty"
            )
        if len(self.data) > MAX_IMAGE_BYTES:
            raise VisionModelError(
                VisionModelErrorCode.INVALID_IMAGE,
                f"image data exceeds the {MAX_IMAGE_BYTES}-byte limit",
            )


@dataclass(frozen=True)
class VisionModelConfig:
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


class VisionModelClient(Protocol):
    def generate(self, request: VisionModelRequest) -> VisionModelResponse: ...


_STRIPPED_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "default",
        "format",
        "title",
        "$defs",
        "$id",
        "$schema",
    }
)


def _strictify(
    node: Any, defs: dict[str, Any], *, property_map: bool = False
) -> Any:
    """Recursively inline $refs and enforce strict-mode constraints in place."""
    if isinstance(node, list):
        return [_strictify(item, defs) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ValueError(f"unsupported schema reference {ref!r}")
        target = defs[ref.removeprefix("#/$defs/")]
        return _strictify(target, defs)

    schema = {
        key: _strictify(value, defs, property_map=key == "properties")
        for key, value in node.items()
        if property_map or key not in _STRIPPED_KEYWORDS
    }
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"])
    return schema


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive a strict structured-output schema from a Pydantic model.

    Inlines ``$defs``/``$ref``, closes every object
    (``additionalProperties: false``), marks all properties required, and strips
    keywords strict mode rejects.
    """
    raw = model.model_json_schema(by_alias=True)
    defs = raw.get("$defs", {})
    return _strictify(raw, defs)
