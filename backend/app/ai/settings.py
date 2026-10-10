"""Centralized AI provider/model configuration.

Pure configuration only: loading these models never constructs SDK clients
and never performs network I/O.
"""

import logging
import os
import re
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.ai.config.loader import (
    load_ai_config_file,
    missing_secret_problems,
    resolve_credential_secrets,
    select_credential,
)
from app.ai.config.models import (
    AiConfig,
    AiConfigurationError,
    AiFeature,
    AiProvider,
)

logger = logging.getLogger(__name__)

AI_CONFIG_FILE_VAR = "AI_CONFIG_FILE"
DEFAULT_AI_CONFIG_FILE = Path(__file__).resolve().parents[2] / "ai.toml"


class AiMode(StrEnum):
    REAL = "real"
    DEMO = "demo"


class ObjectGroundingProvider(StrEnum):
    NONE = "none"
    GROUNDING_DINO = "groundingDino"


class ImageModerationProvider(StrEnum):
    NONE = "none"
    OPENAI = "openai"


class FeatureModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature: AiFeature
    provider: AiProvider
    model_name: str = ""
    timeout_seconds: int = Field(gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_retries: int = Field(default=0, ge=0)
    temperature: float = Field(default=0.0, ge=0, le=2)
    deployment_id: str = ""
    credential_id: str = ""


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    base_url: str = "https://cloud.langfuse.com"
    public_key: str = ""
    secret_key: str = Field(default="", repr=False)
    environment: str = "development"
    capture_content: bool = False


class ObjectGroundingSettings(BaseModel):
    """Configuration for the optional local location-refinement pass."""

    model_config = ConfigDict(frozen=True)

    provider: ObjectGroundingProvider = ObjectGroundingProvider.NONE
    model_name: str = ""
    threshold: float = Field(default=0.35, ge=0, le=1)
    max_labels: int = Field(default=12, gt=0)
    max_image_side: int = Field(default=1024, gt=0)


class ImageModerationSettings(BaseModel):
    """Configuration for the optional upload-image moderation pass."""

    model_config = ConfigDict(frozen=True)

    provider: ImageModerationProvider = ImageModerationProvider.NONE
    model_name: str = ""
    timeout_seconds: int = Field(default=30, gt=0)


class ResultCacheSettings(BaseModel):
    """Bounds for the in-process validated-result cache."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    ttl_seconds: int = 86_400
    max_entries: int = 2_000


class AiSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: AiMode
    ai_config: AiConfig | None = None
    credential_secrets: dict[str, str] = Field(default_factory=dict, repr=False)
    observability: ObservabilitySettings = ObservabilitySettings()
    object_grounding: ObjectGroundingSettings = ObjectGroundingSettings()
    image_moderation: ImageModerationSettings = ImageModerationSettings()
    result_cache: ResultCacheSettings = ResultCacheSettings()
    scene_analysis: FeatureModelConfig
    scene_translation: FeatureModelConfig
    learning_task: FeatureModelConfig
    ispy_clue: FeatureModelConfig
    ispy_guess: FeatureModelConfig

    def api_key_for(self, provider: AiProvider) -> str:
        """The first available secret among the credentials for ``provider``."""
        if self.ai_config is None:
            return ""
        for credential_id, credential in self.ai_config.credentials.items():
            secret = self.credential_secrets.get(credential_id)
            if credential.adapter is provider and secret:
                return secret
        return ""

    def secret_for(self, config: FeatureModelConfig) -> str:
        """The secret of the credential selected for a feature's deployment."""
        return self.credential_secrets.get(config.credential_id, "")

    def is_configured(self, config: FeatureModelConfig) -> bool:
        return (
            config.provider is not AiProvider.NONE
            and bool(config.model_name)
            and bool(self.secret_for(config))
        )

    def feature(self, feature: AiFeature) -> FeatureModelConfig:
        return getattr(self, _FEATURE_FIELDS[feature])


_FEATURE_FIELDS: dict[AiFeature, str] = {
    feature: feature.name.lower() for feature in AiFeature
}


_ALLOWED_MODES = ", ".join(mode.value for mode in AiMode)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_ENVIRONMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    return value.strip() if value is not None else None


def _parse_bool(env: Mapping[str, str], canonical: str, default: bool) -> bool:
    raw = _read(env, canonical)
    if raw is None or raw == "":
        return default
    lowered = raw.casefold()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise AiConfigurationError(
        f"Invalid boolean for {canonical}: {raw!r} "
        "(allowed: 1/true/yes/on or 0/false/no/off)"
    )


def _parse_observability(env: Mapping[str, str]) -> ObservabilitySettings:
    environment = (
        _read(env, "AI_OBSERVABILITY_ENVIRONMENT") or "development"
    )
    if not _ENVIRONMENT_PATTERN.fullmatch(environment) or environment.startswith(
        "langfuse"
    ):
        raise AiConfigurationError(
            f"Invalid observability environment: {environment!r} "
            "(must match ^[a-z0-9][a-z0-9_-]*$ and not start with 'langfuse')"
        )
    return ObservabilitySettings(
        enabled=_parse_bool(env, "AI_OBSERVABILITY_ENABLED", False),
        base_url=_read(env, "AI_OBSERVABILITY_BASE_URL")
        or "https://cloud.langfuse.com",
        public_key=_read(env, "AI_OBSERVABILITY_PUBLIC_KEY") or "",
        secret_key=_read(env, "AI_OBSERVABILITY_SECRET_KEY") or "",
        environment=environment,
        capture_content=_parse_bool(env, "AI_OBSERVABILITY_CAPTURE_CONTENT", False),
    )


def _parse_object_grounding(env: Mapping[str, str]) -> ObjectGroundingSettings:
    raw_provider = (_read(env, "AI_OBJECT_GROUNDING_PROVIDER") or "none").casefold()
    provider_aliases = {"groundingdino": ObjectGroundingProvider.GROUNDING_DINO}
    provider = provider_aliases.get(raw_provider)
    if provider is None:
        try:
            provider = ObjectGroundingProvider(raw_provider)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ObjectGroundingProvider)
            raise AiConfigurationError(
                "Invalid object grounding provider: "
                f"{raw_provider!r} (allowed: {allowed})"
            ) from exc
    raw_threshold = _read(env, "AI_OBJECT_GROUNDING_THRESHOLD") or "0.35"
    try:
        threshold = float(raw_threshold)
    except ValueError as exc:
        raise AiConfigurationError(
            "Invalid object grounding threshold: "
            f"{raw_threshold!r} (AI_OBJECT_GROUNDING_THRESHOLD must be 0..1)"
        ) from exc
    model_name = _read(env, "AI_OBJECT_GROUNDING_MODEL") or (
        "IDEA-Research/grounding-dino-base"
        if provider is ObjectGroundingProvider.GROUNDING_DINO
        else ""
    )
    try:
        return ObjectGroundingSettings(
            provider=provider,
            model_name=model_name,
            threshold=threshold,
            max_labels=_parse_positive_int(
                env,
                "AI_OBJECT_GROUNDING_MAX_LABELS",
                12,
                "object grounding max labels",
            ),
            max_image_side=_parse_positive_int(
                env,
                "AI_OBJECT_GROUNDING_MAX_IMAGE_SIDE",
                1024,
                "object grounding max image side",
            ),
        )
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid object grounding configuration: {exc}"
        ) from exc


def _parse_positive_int(
    env: Mapping[str, str], name: str, default: int, kind: str
) -> int:
    raw = _read(env, name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid {kind}: {raw!r} ({name} must be a positive integer)"
        ) from exc
    if value <= 0:
        raise AiConfigurationError(
            f"Invalid {kind}: {raw!r} ({name} must be a positive integer)"
        )
    return value


def _parse_result_cache(env: Mapping[str, str]) -> ResultCacheSettings:
    return ResultCacheSettings(
        enabled=_parse_bool(env, "AI_RESULT_CACHE_ENABLED", True),
        ttl_seconds=_parse_positive_int(
            env, "AI_RESULT_CACHE_TTL_SECONDS", 86_400, "result cache TTL"
        ),
        max_entries=_parse_positive_int(
            env, "AI_RESULT_CACHE_MAX_ENTRIES", 2_000, "result cache capacity"
        ),
    )


def _parse_image_moderation(env: Mapping[str, str]) -> ImageModerationSettings:
    raw_provider = (_read(env, "AI_IMAGE_MODERATION_PROVIDER") or "none").casefold()
    try:
        provider = ImageModerationProvider(raw_provider)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ImageModerationProvider)
        raise AiConfigurationError(
            "Invalid image moderation provider: "
            f"{raw_provider!r} (allowed: {allowed})"
        ) from exc
    model_name = _read(env, "AI_IMAGE_MODERATION_MODEL") or (
        "omni-moderation-latest"
        if provider is ImageModerationProvider.OPENAI
        else ""
    )
    raw_timeout = _read(env, "AI_IMAGE_MODERATION_TIMEOUT_SECONDS") or "30"
    try:
        timeout_seconds = int(raw_timeout)
    except ValueError as exc:
        raise AiConfigurationError(
            "Invalid timeout for imageModeration: "
            f"{raw_timeout!r} (AI_IMAGE_MODERATION_TIMEOUT_SECONDS must be a "
            "positive integer number of seconds)"
        ) from exc
    if timeout_seconds <= 0:
        raise AiConfigurationError(
            "Invalid timeout for imageModeration: "
            f"{raw_timeout!r} (AI_IMAGE_MODERATION_TIMEOUT_SECONDS must be a "
            "positive integer number of seconds)"
        )
    try:
        return ImageModerationSettings(
            provider=provider,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid image moderation configuration: {exc}"
        ) from exc


def _features_from_config(
    config: AiConfig, secrets: Mapping[str, str]
) -> dict[AiFeature, FeatureModelConfig]:
    features: dict[AiFeature, FeatureModelConfig] = {}
    for feature in AiFeature:
        primary = config.primary_deployment(feature)
        if primary is None:
            features[feature] = FeatureModelConfig(
                feature=feature,
                provider=AiProvider.NONE,
                timeout_seconds=60,
            )
            continue
        deployment_id, deployment = primary
        defaults = deployment.defaults
        features[feature] = FeatureModelConfig(
            feature=feature,
            provider=deployment.adapter,
            model_name=deployment.model,
            timeout_seconds=defaults.timeout_seconds,
            max_output_tokens=defaults.max_output_tokens,
            max_retries=defaults.max_retries,
            temperature=defaults.temperature,
            deployment_id=deployment_id,
            credential_id=select_credential(config, deployment.credentials, secrets),
        )
    return features


def load_ai_settings(env: Mapping[str, str] | None = None) -> AiSettings:
    """Load AI settings from ``env`` (defaults to ``os.environ``).

    Credentials, deployments and routes come from the TOML file named by
    ``AI_CONFIG_FILE``, else ``backend/ai.toml``. Secrets, the mode, the result
    cache, observability, moderation and object grounding come from ``env``.
    Pure: never constructs SDK clients or opens sockets.
    """
    if env is None:
        env = os.environ

    raw_mode = (_read(env, "AI_MODE") or AiMode.DEMO.value).casefold()
    try:
        mode = AiMode(raw_mode)
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid AI_MODE: {raw_mode!r} (allowed: {_ALLOWED_MODES})"
        ) from exc

    ai_config = load_ai_config_file(_read(env, AI_CONFIG_FILE_VAR) or DEFAULT_AI_CONFIG_FILE)
    secrets = resolve_credential_secrets(ai_config, env)
    features = _features_from_config(ai_config, secrets)
    settings = AiSettings(
        mode=mode,
        observability=_parse_observability(env),
        object_grounding=_parse_object_grounding(env),
        image_moderation=_parse_image_moderation(env),
        result_cache=_parse_result_cache(env),
        ai_config=ai_config,
        credential_secrets=secrets,
        **{_FEATURE_FIELDS[feature]: config for feature, config in features.items()},
    )

    if settings.mode is AiMode.REAL:
        problems = missing_secret_problems(ai_config, secrets)
        if (
            settings.image_moderation.provider is ImageModerationProvider.OPENAI
            and not settings.api_key_for(AiProvider.OPENAI)
        ):
            problems.append(
                "imageModeration: missing openai API key "
                "(set AI_OPENAI_API_KEY)"
            )
        observability = settings.observability
        if observability.enabled:
            if not observability.public_key:
                problems.append(
                    "observability: missing Langfuse public key "
                    "(set AI_OBSERVABILITY_PUBLIC_KEY)"
                )
            if not observability.secret_key:
                problems.append(
                    "observability: missing Langfuse secret key "
                    "(set AI_OBSERVABILITY_SECRET_KEY)"
                )
        if problems:
            raise AiConfigurationError(
                "AI_MODE=real requires complete AI configuration: "
                + "; ".join(problems)
            )

    return settings
