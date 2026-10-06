"""Provider-independent contracts shared by AI adapters and feature services."""

from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.metadata import FinishStatus, ResponseMetadata, TokenUsage
from app.ai.contracts.schema import build_strict_json_schema
from app.ai.contracts.text import (
    TextModelClient,
    TextModelConfig,
    TextModelRequest,
    TextModelResponse,
)
from app.ai.contracts.vision import (
    ALLOWED_IMAGE_MIME_TYPES,
    VisionImage,
    VisionModelClient,
    VisionModelConfig,
    VisionModelRequest,
    VisionModelResponse,
)

__all__ = [
    "ALLOWED_IMAGE_MIME_TYPES",
    "FinishStatus",
    "ModelConfig",
    "ProviderError",
    "ProviderErrorCode",
    "ProviderFailureScope",
    "ResponseMetadata",
    "TextModelClient",
    "TextModelConfig",
    "TextModelRequest",
    "TextModelResponse",
    "TokenUsage",
    "VisionImage",
    "VisionModelClient",
    "VisionModelConfig",
    "VisionModelRequest",
    "VisionModelResponse",
    "build_strict_json_schema",
]
