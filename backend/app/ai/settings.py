"""Centralized AI provider/model configuration.

Pure configuration only: loading these models never constructs SDK clients
and never performs network I/O.
"""

import os
import re
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AiMode(StrEnum):
    REAL = "real"
    DEMO = "demo"


class AiProvider(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    # OpenRouter fronts many vendors (Anthropic, Qwen, DeepSeek, Meta,
    # Mistral) behind an OpenAI-compatible API, so the OpenAI adapters serve
    # it with a different base URL and key.
    OPENROUTER = "openrouter"
    NONE = "none"


class ObjectGroundingProvider(StrEnum):
    NONE = "none"
    GROUNDING_DINO = "groundingDino"


class ImageModerationProvider(StrEnum):
    NONE = "none"
    OPENAI = "openai"


class AiFeature(StrEnum):
    SCENE_ANALYSIS = "sceneAnalysis"
    SCENE_TRANSLATION = "sceneTranslation"
    LEARNING_TASK = "learningTask"
    ISPY_CLUE = "ispyClue"
    ISPY_GUESS = "ispyGuess"


class AiConfigurationError(ValueError):
    """Raised when AI environment configuration is invalid."""


class FeatureModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature: AiFeature
    provider: AiProvider
    model_name: str = ""
    timeout_seconds: int = Field(gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_retries: int = Field(default=0, ge=0)


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    base_url: str = "https://cloud.langfuse.com"
    public_key: str = ""
    secret_key: str = ""
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


class AiSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: AiMode
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    general_api_key: str = ""
    observability: ObservabilitySettings = ObservabilitySettings()
    object_grounding: ObjectGroundingSettings = ObjectGroundingSettings()
    image_moderation: ImageModerationSettings = ImageModerationSettings()
    scene_analysis: FeatureModelConfig
    scene_translation: FeatureModelConfig
    learning_task: FeatureModelConfig
    ispy_clue: FeatureModelConfig
    ispy_guess: FeatureModelConfig

    def api_key_for(self, provider: AiProvider) -> str:
        if provider is AiProvider.OPENAI:
            return self.openai_api_key
        if provider is AiProvider.GEMINI:
            return self.gemini_api_key
        if provider is AiProvider.OPENROUTER:
            return self.openrouter_api_key
        return ""

    def is_configured(self, config: FeatureModelConfig) -> bool:
        return (
            config.provider is not AiProvider.NONE
            and bool(config.model_name)
            and bool(self.api_key_for(config.provider))
        )

    def feature(self, feature: AiFeature) -> FeatureModelConfig:
        return getattr(self, _FEATURE_FIELDS[feature])


_FEATURE_FIELDS: dict[AiFeature, str] = {
    feature: feature.name.lower() for feature in AiFeature
}


class _LegacySpec:
    """Legacy environment variable names and defaults for one feature."""

    def __init__(
        self,
        provider_var: str,
        provider_default: str,
        timeout_var: str,
        timeout_default: str,
        model_vars: dict[AiProvider, str],
        model_defaults: dict[AiProvider, str],
    ) -> None:
        self.provider_var = provider_var
        self.provider_default = provider_default
        self.timeout_var = timeout_var
        self.timeout_default = timeout_default
        self.model_vars = model_vars
        self.model_defaults = model_defaults


_LEGACY_SPECS: dict[AiFeature, _LegacySpec] = {
    AiFeature.SCENE_ANALYSIS: _LegacySpec(
        provider_var="SCENE_ANALYSIS_PROVIDER",
        provider_default="openrouter",
        timeout_var="SCENE_ANALYSIS_TIMEOUT_SECONDS",
        timeout_default="120",
        model_vars={
            AiProvider.OPENAI: "OPENAI_SCENE_MODEL",
            AiProvider.GEMINI: "GEMINI_SCENE_MODEL",
            AiProvider.OPENROUTER: "OPENROUTER_SCENE_MODEL",
        },
        model_defaults={
            AiProvider.OPENAI: "gpt-4o",
            AiProvider.GEMINI: "",
            AiProvider.OPENROUTER: "anthropic/claude-haiku-4.5",
        },
    ),
    AiFeature.SCENE_TRANSLATION: _LegacySpec(
        provider_var="TRANSLATION_PROVIDER",
        provider_default="openrouter",
        timeout_var="TRANSLATION_TIMEOUT_SECONDS",
        timeout_default="60",
        model_vars={
            AiProvider.OPENAI: "OPENAI_TRANSLATION_MODEL",
            AiProvider.GEMINI: "GEMINI_TRANSLATION_MODEL",
            AiProvider.OPENROUTER: "OPENROUTER_TRANSLATION_MODEL",
        },
        model_defaults={
            AiProvider.OPENAI: "gpt-4o-mini",
            AiProvider.GEMINI: "gemini-3.5-flash-lite",
            # Mistral Small scored marginally higher but is served only by
            # Mistral and rate-limited upstream too often to be the default.
            AiProvider.OPENROUTER: "openai/gpt-4o-mini",
        },
    ),
    AiFeature.LEARNING_TASK: _LegacySpec(
        provider_var="LEARNING_TASK_PROVIDER",
        provider_default="openrouter",
        timeout_var="LEARNING_TASK_TIMEOUT_SECONDS",
        timeout_default="60",
        model_vars={
            AiProvider.OPENAI: "OPENAI_LEARNING_TASK_MODEL",
            AiProvider.GEMINI: "GEMINI_LEARNING_TASK_MODEL",
            AiProvider.OPENROUTER: "OPENROUTER_LEARNING_TASK_MODEL",
        },
        model_defaults={
            AiProvider.OPENAI: "gpt-5.4-mini",
            AiProvider.GEMINI: "gemini-3.5-flash-lite",
            AiProvider.OPENROUTER: "openai/gpt-5.4-mini",
        },
    ),
    AiFeature.ISPY_CLUE: _LegacySpec(
        provider_var="ISPY_CLUE_PROVIDER",
        provider_default="openrouter",
        timeout_var="ISPY_CLUE_TIMEOUT_SECONDS",
        timeout_default="60",
        model_vars={
            AiProvider.OPENAI: "OPENAI_ISPY_CLUE_MODEL",
            AiProvider.GEMINI: "GEMINI_ISPY_CLUE_MODEL",
            AiProvider.OPENROUTER: "OPENROUTER_ISPY_CLUE_MODEL",
        },
        model_defaults={
            AiProvider.OPENAI: "gpt-4o-mini",
            AiProvider.GEMINI: "gemini-3.1-flash-lite",
            AiProvider.OPENROUTER: "google/gemini-3.1-flash-lite",
        },
    ),
    AiFeature.ISPY_GUESS: _LegacySpec(
        provider_var="ISPY_GUESS_PROVIDER",
        provider_default="openrouter",
        timeout_var="ISPY_GUESS_TIMEOUT_SECONDS",
        timeout_default="60",
        model_vars={
            AiProvider.OPENAI: "OPENAI_ISPY_GUESS_MODEL",
            AiProvider.OPENROUTER: "OPENROUTER_ISPY_GUESS_MODEL",
        },
        model_defaults={
            AiProvider.OPENAI: "gpt-4.1-mini",
            AiProvider.OPENROUTER: "openai/gpt-4.1-mini",
        },
    ),
}

_ALLOWED_PROVIDERS = ", ".join(provider.value for provider in AiProvider)
_ALLOWED_MODES = ", ".join(mode.value for mode in AiMode)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_ENVIRONMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

_OBSERVABILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "AI_OBSERVABILITY_ENABLED": ("LANGFUSE_TRACING_ENABLED",),
    "AI_OBSERVABILITY_BASE_URL": ("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    "AI_OBSERVABILITY_PUBLIC_KEY": ("LANGFUSE_PUBLIC_KEY",),
    "AI_OBSERVABILITY_SECRET_KEY": ("LANGFUSE_SECRET_KEY",),
    "AI_OBSERVABILITY_ENVIRONMENT": ("LANGFUSE_TRACING_ENVIRONMENT",),
    "AI_OBSERVABILITY_CAPTURE_CONTENT": (),
}


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    return value.strip() if value is not None else None


def _parse_provider(env: Mapping[str, str], feature: AiFeature, stem: str) -> AiProvider:
    spec = _LEGACY_SPECS[feature]
    raw = (
        _read(env, f"AI_{stem}_PROVIDER")
        or _read(env, spec.provider_var)
        or spec.provider_default
    ).casefold()
    try:
        return AiProvider(raw)
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid provider for {feature.value}: {raw!r} "
            f"(allowed: {_ALLOWED_PROVIDERS})"
        ) from exc


def _parse_timeout(
    env: Mapping[str, str], feature: AiFeature, stem: str
) -> int:
    spec = _LEGACY_SPECS[feature]
    canonical = f"AI_{stem}_TIMEOUT_SECONDS"
    raw = _read(env, canonical) or _read(env, spec.timeout_var) or spec.timeout_default
    try:
        value = int(raw)
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid timeout for {feature.value}: {raw!r} "
            f"({canonical} must be a positive integer number of seconds)"
        ) from exc
    if value <= 0:
        raise AiConfigurationError(
            f"Invalid timeout for {feature.value}: {raw!r} "
            f"({canonical} must be a positive integer number of seconds)"
        )
    return value


def _parse_int(
    env: Mapping[str, str], feature: AiFeature, name: str, kind: str
) -> int | None:
    raw = _read(env, name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid {kind} for {feature.value}: {raw!r} ({name} must be an integer)"
        ) from exc


def _read_with_aliases(env: Mapping[str, str], canonical: str) -> str | None:
    value = _read(env, canonical)
    if value is not None:
        return value
    for alias in _OBSERVABILITY_ALIASES[canonical]:
        value = _read(env, alias)
        if value is not None:
            return value
    return None


def _parse_bool(env: Mapping[str, str], canonical: str, default: bool) -> bool:
    raw = _read_with_aliases(env, canonical)
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
        _read_with_aliases(env, "AI_OBSERVABILITY_ENVIRONMENT") or "development"
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
        base_url=_read_with_aliases(env, "AI_OBSERVABILITY_BASE_URL")
        or "https://cloud.langfuse.com",
        public_key=_read_with_aliases(env, "AI_OBSERVABILITY_PUBLIC_KEY") or "",
        secret_key=_read_with_aliases(env, "AI_OBSERVABILITY_SECRET_KEY") or "",
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


def _parse_model(
    env: Mapping[str, str], feature: AiFeature, stem: str, provider: AiProvider
) -> str:
    canonical = _read(env, f"AI_{stem}_MODEL")
    if canonical is not None:
        return canonical
    spec = _LEGACY_SPECS[feature]
    legacy_var = spec.model_vars.get(provider)
    if legacy_var is not None:
        legacy = _read(env, legacy_var)
        if legacy is not None:
            return legacy
    return spec.model_defaults.get(provider, "")


def _load_feature(
    env: Mapping[str, str], feature: AiFeature
) -> FeatureModelConfig:
    stem = feature.name
    provider = _parse_provider(env, feature, stem)
    max_retries = _parse_int(env, feature, f"AI_{stem}_MAX_RETRIES", "max retries")
    max_output_tokens = _parse_int(
        env, feature, f"AI_{stem}_MAX_OUTPUT_TOKENS", "max output tokens"
    )
    try:
        return FeatureModelConfig(
            feature=feature,
            provider=provider,
            model_name=_parse_model(env, feature, stem, provider),
            timeout_seconds=_parse_timeout(env, feature, stem),
            max_output_tokens=max_output_tokens,
            # Translations, lessons and I-Spy clues are structured responses. One
            # repair attempt avoids replacing a usable session when a provider
            # misses a non-schema constraint; an explicit 0 still disables it.
            max_retries=(
                1
                if max_retries is None
                and feature in {
                    AiFeature.SCENE_TRANSLATION, AiFeature.LEARNING_TASK, AiFeature.ISPY_CLUE
                }
                else 0 if max_retries is None else max_retries
            ),
        )
    except ValueError as exc:
        raise AiConfigurationError(
            f"Invalid configuration for {feature.value}: {exc}"
        ) from exc


def load_ai_settings(env: Mapping[str, str] | None = None) -> AiSettings:
    """Load AI settings from ``env`` (defaults to ``os.environ``).

    Pure: reads only the given mapping. Never constructs SDK clients or
    opens sockets.
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

    settings = AiSettings(
        mode=mode,
        openai_api_key=_read(env, "AI_OPENAI_API_KEY")
        or _read(env, "OPENAI_API_KEY")
        or "",
        gemini_api_key=_read(env, "AI_GEMINI_API_KEY")
        or _read(env, "GEMINI_API_KEY")
        or "",
        openrouter_api_key=_read(env, "AI_OPENROUTER_API_KEY")
        or _read(env, "OPENROUTER_API_KEY")
        or "",
        general_api_key=_read(env, "AI_API_KEY") or "",
        observability=_parse_observability(env),
        object_grounding=_parse_object_grounding(env),
        image_moderation=_parse_image_moderation(env),
        **{
            field: _load_feature(env, feature)
            for feature, field in _FEATURE_FIELDS.items()
        },
    )

    if settings.mode is AiMode.REAL:
        problems: list[str] = []
        for feature, field in _FEATURE_FIELDS.items():
            config = getattr(settings, field)
            if config.provider is AiProvider.NONE:
                continue
            stem = feature.name
            if not config.model_name:
                problems.append(
                    f"{feature.value}: missing model name (set AI_{stem}_MODEL)"
                )
            if not settings.api_key_for(config.provider):
                key_var = f"AI_{config.provider.value.upper()}_API_KEY"
                problems.append(
                    f"{feature.value}: missing {config.provider.value} API key "
                    f"(set {key_var})"
                )
        if (
            settings.image_moderation.provider is ImageModerationProvider.OPENAI
            and not settings.openai_api_key
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
