"""Non-secret AI configuration: credentials, deployments and feature routes.

Credentials name the environment variables that hold a secret; the secret
itself never appears in this configuration.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class AiProvider(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    NONE = "none"


class AiFeature(StrEnum):
    SCENE_ANALYSIS = "sceneAnalysis"
    SCENE_TRANSLATION = "sceneTranslation"
    LEARNING_TASK = "learningTask"
    ISPY_CLUE = "ispyClue"
    ISPY_GUESS = "ispyGuess"


class AiConfigurationError(ValueError):
    """Raised when AI configuration is invalid."""


class ApiType(StrEnum):
    RESPONSES = "responses"
    GENERATE_CONTENT = "generateContent"


class Capability(StrEnum):
    TEXT = "text"
    VISION = "vision"
    JSON_SCHEMA = "jsonSchema"


class SelectionPolicy(StrEnum):
    PRIMARY = "primary"
    """Use only the first deployment, rotating its credentials."""
    PRIORITY = "priority"
    """Try deployments in listed order, failing over on transient errors."""


@dataclass(frozen=True)
class AdapterSpec:
    apis: frozenset[ApiType]
    capabilities: frozenset[Capability]


ADAPTERS: dict[AiProvider, AdapterSpec] = {
    AiProvider.OPENAI: AdapterSpec(frozenset({ApiType.RESPONSES}), frozenset(Capability)),
    AiProvider.OPENROUTER: AdapterSpec(frozenset({ApiType.RESPONSES}), frozenset(Capability)),
    AiProvider.GEMINI: AdapterSpec(
        frozenset({ApiType.GENERATE_CONTENT}), frozenset(Capability)
    ),
}

DEFAULT_API: dict[AiProvider, ApiType] = {
    AiProvider.OPENAI: ApiType.RESPONSES,
    AiProvider.OPENROUTER: ApiType.RESPONSES,
    AiProvider.GEMINI: ApiType.GENERATE_CONTENT,
}

FEATURE_CAPABILITIES: dict[AiFeature, frozenset[Capability]] = {
    feature: frozenset({Capability.TEXT, Capability.JSON_SCHEMA})
    for feature in AiFeature
} | {
    AiFeature.SCENE_ANALYSIS: frozenset({Capability.VISION, Capability.JSON_SCHEMA}),
}

ConfigId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
EnvVarName = Annotated[str, StringConstraints(pattern=r"^[A-Z_][A-Z0-9_]*$")]


class _Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CredentialConfig(_Config):
    adapter: AiProvider
    env: tuple[EnvVarName, ...] = Field(min_length=1)
    quota_group: str = Field(min_length=1)
    billing_group: str = Field(min_length=1)


class GenerationDefaults(_Config):
    timeout_seconds: int = Field(gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_retries: int = Field(default=0, ge=0)
    temperature: float = Field(default=0.0, ge=0, le=2)


class UpstreamFallback(_Config):
    """OpenRouter's own fallback, inside one outbound request."""

    allow_fallbacks: bool
    models: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = ()


class DeploymentConfig(_Config):
    adapter: AiProvider
    api: ApiType
    model: str = Field(min_length=1)
    capabilities: frozenset[Capability] = Field(min_length=1)
    credentials: tuple[ConfigId, ...] = Field(min_length=1)
    defaults: GenerationDefaults
    upstream_fallback: UpstreamFallback | None = None
    """Required for OpenRouter deployments, rejected for others."""


class RouteConfig(_Config):
    enabled: bool = True
    deployments: tuple[ConfigId, ...] = ()
    policy: SelectionPolicy = SelectionPolicy.PRIMARY
    deadline_seconds: int | None = Field(default=None, gt=0)
    max_model_calls: int | None = Field(default=None, ge=1)


class AiConfig(_Config):
    credentials: dict[ConfigId, CredentialConfig] = Field(default_factory=dict)
    deployments: dict[ConfigId, DeploymentConfig] = Field(default_factory=dict)
    routes: dict[AiFeature, RouteConfig]

    def primary_deployment(self, feature: AiFeature) -> tuple[str, DeploymentConfig] | None:
        """The deployment the ``primary`` policy selects, or ``None`` when off."""
        route = self.routes.get(feature)
        if route is None or not route.enabled or not route.deployments:
            return None
        deployment_id = route.deployments[0]
        return deployment_id, self.deployments[deployment_id]
