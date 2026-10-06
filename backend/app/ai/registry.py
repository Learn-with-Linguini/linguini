"""Provider-neutral client/service construction from centralized AI settings.

Reads only ``AiSettings`` — providers and models are never chosen anywhere
else. Returns ``None`` for features configured off so callers keep their
deterministic fallbacks.
"""

from __future__ import annotations

from typing import Any

from app.ai.adapters.gemini import GeminiTextClient, GeminiVisionClient
from app.ai.adapters.openai import OpenAITextClient, OpenAIVisionClient
from app.ai.adapters.openrouter import OpenRouterTextClient, OpenRouterVisionClient
from app.ai.config.models import DeploymentConfig, SelectionPolicy, UpstreamFallback
from app.ai.contracts import VisionModelClient, VisionModelConfig
from app.ai.contracts.config import ModelConfig
from app.ai.contracts.text import TextModelClient, TextModelConfig
from app.ai.features.ispy_clues import ISpyClueService
from app.ai.features.ispy_guess import ISpyGuessService
from app.ai.features.learning_tasks import LearningTaskService
from app.ai.features.moderation import ImageModerator, OpenAIImageModerator
from app.ai.features.object_grounding import GroundingDinoObjectGrounder, ObjectGrounder
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.features.translation import SceneTranslationService
from app.ai.observability import AITracer
from app.ai.pool import ProviderPool
from app.ai.routing import RoutedModelClient, RouteTarget, as_routed
from app.ai.settings import (
    AiFeature,
    AiProvider,
    AiSettings,
    ImageModerationProvider,
    ObjectGroundingProvider,
)
from app.services.image_storage import ImageStorage


def build_text_client(
    provider: AiProvider,
    settings: AiSettings,
    config: TextModelConfig,
    *,
    api_key: str | None = None,
    upstream_fallback: UpstreamFallback | None = None,
) -> TextModelClient:
    key = settings.api_key_for(provider) if api_key is None else api_key
    if provider is AiProvider.OPENAI:
        return OpenAITextClient(key, config)
    if provider is AiProvider.GEMINI:
        return GeminiTextClient(key, config)
    if provider is AiProvider.OPENROUTER:
        return OpenRouterTextClient(key, config, **_openrouter_options(upstream_fallback))
    raise ValueError(f"unsupported text provider {provider!r}")


def build_vision_client(
    provider: AiProvider,
    settings: AiSettings,
    config: VisionModelConfig,
    *,
    api_key: str | None = None,
    upstream_fallback: UpstreamFallback | None = None,
) -> VisionModelClient:
    key = settings.api_key_for(provider) if api_key is None else api_key
    if provider is AiProvider.OPENAI:
        return OpenAIVisionClient(key, config)
    if provider is AiProvider.GEMINI:
        return GeminiVisionClient(key, config)
    if provider is AiProvider.OPENROUTER:
        return OpenRouterVisionClient(key, config, **_openrouter_options(upstream_fallback))
    raise ValueError(f"unsupported vision provider {provider!r}")


def _openrouter_options(upstream_fallback: UpstreamFallback | None) -> dict[str, Any]:
    if upstream_fallback is None:
        return {}
    return {
        "allow_fallbacks": upstream_fallback.allow_fallbacks,
        "fallback_models": upstream_fallback.models,
    }


def _model_config(model: str, defaults: Any, default_max_output_tokens: int) -> ModelConfig:
    return ModelConfig(
        model_name=model,
        timeout_seconds=defaults.timeout_seconds,
        max_output_tokens=defaults.max_output_tokens or default_max_output_tokens,
        max_retries=min(defaults.max_retries, 1),
        temperature=defaults.temperature,
    )


def _route_target(
    kind: str,
    settings: AiSettings,
    deployment_id: str,
    deployment: DeploymentConfig,
    default_max_output_tokens: int,
) -> RouteTarget:
    build = build_text_client if kind == "text" else build_vision_client
    config = _model_config(deployment.model, deployment.defaults, default_max_output_tokens)
    return RouteTarget(
        deployment_id,
        deployment.adapter.value,
        config,
        lambda secret: build(
            deployment.adapter,
            settings,
            config,
            api_key=secret,
            upstream_fallback=deployment.upstream_fallback,
        ),
    )


def build_routed_client(
    kind: str,
    settings: AiSettings,
    feature: AiFeature,
    *,
    default_max_output_tokens: int = 1500,
    pool: ProviderPool | None = None,
    tracer: AITracer | None = None,
) -> tuple[RoutedModelClient, ModelConfig]:
    """The feature's routed client and its primary deployment's settings.

    Clients are built lazily on first use. Settings without a configured
    route fall back to one directly built client.
    """
    feature_config = settings.feature(feature)
    pool = pool or ProviderPool.from_settings(settings)
    route = settings.ai_config.routes.get(feature) if settings.ai_config else None
    if route is None or not route.deployments or not all(
        pool.credentials.has_deployment(deployment_id) for deployment_id in route.deployments
    ):
        config = _model_config(
            feature_config.model_name, feature_config, default_max_output_tokens
        )
        build = build_text_client if kind == "text" else build_vision_client
        client = build(
            feature_config.provider, settings, config, api_key=settings.secret_for(feature_config)
        )
        return as_routed(client, config, kind=kind), config
    deployment_ids = (
        route.deployments
        if route.policy is SelectionPolicy.PRIORITY
        else route.deployments[:1]
    )
    targets = tuple(
        _route_target(
            kind,
            settings,
            deployment_id,
            settings.ai_config.deployments[deployment_id],
            default_max_output_tokens,
        )
        for deployment_id in deployment_ids
    )
    primary = targets[0].config
    client = RoutedModelClient(
        kind,
        targets,
        pool.credentials,
        max_model_calls=route.max_model_calls or 1 + primary.max_retries,
        deadline_seconds=route.deadline_seconds,
        clients=pool.clients,
        tracer=tracer,
    )
    return client, primary


def build_uploaded_scene_analyzer(
    settings: AiSettings,
    storage: ImageStorage,
    tracer: AITracer,
    object_grounder: ObjectGrounder | None = None,
    image_moderator: ImageModerator | None = None,
    pool: ProviderPool | None = None,
) -> UploadedSceneAnalyzer | None:
    """Build the configured uploaded-photo analyzer, or ``None`` when off.

    ``None`` preserves the workflow's deterministic scene fallback. The
    caller routes only non-preloaded media through the returned analyzer.
    """
    scene_config = settings.feature(AiFeature.SCENE_ANALYSIS)
    if scene_config.provider in (
        AiProvider.OPENAI, AiProvider.GEMINI, AiProvider.OPENROUTER
    ):
        if not settings.is_configured(scene_config):
            return None
        client, vision_config = build_routed_client(
            "vision",
            settings,
            AiFeature.SCENE_ANALYSIS,
            default_max_output_tokens=1500,
            pool=pool,
            tracer=tracer,
        )
        return UploadedSceneAnalyzer(
            storage,
            client,
            vision_config,
            tracer=tracer,
            provider=scene_config.provider.value,
            object_grounder=object_grounder,
            image_moderator=image_moderator,
        )
    if scene_config.provider is AiProvider.NONE:
        return None
    raise ValueError(f"Unsupported SCENE_ANALYSIS_PROVIDER: {scene_config.provider}")


def build_object_grounder(settings: AiSettings) -> ObjectGrounder | None:
    """Build the configured local detector, or leave model coordinates alone."""
    config = settings.object_grounding
    if config.provider is ObjectGroundingProvider.NONE:
        return None
    if config.provider is ObjectGroundingProvider.GROUNDING_DINO:
        return GroundingDinoObjectGrounder(
            config.model_name,
            config.threshold,
            max_labels=config.max_labels,
            max_image_side=config.max_image_side,
        )
    raise ValueError(f"unsupported object grounding provider {config.provider!r}")


def build_image_moderator(settings: AiSettings) -> ImageModerator | None:
    """Build the configured image moderator, or ``None`` when turned off."""
    config = settings.image_moderation
    if config.provider is ImageModerationProvider.NONE:
        return None
    if config.provider is ImageModerationProvider.OPENAI:
        if not settings.openai_api_key:
            return None
        return OpenAIImageModerator(
            settings.openai_api_key,
            config.model_name,
            timeout_seconds=config.timeout_seconds,
        )
    raise ValueError(f"unsupported image moderation provider {config.provider!r}")


def build_scene_translator(
    settings: AiSettings, tracer: AITracer, *, pool: ProviderPool | None = None
) -> SceneTranslationService | None:
    """Build the configured scene translator, or ``None`` when turned off.

    ``None`` preserves the workflow's deterministic offline fallback.
    """
    config = settings.feature(AiFeature.SCENE_TRANSLATION)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    client, text_config = build_routed_client(
        "text",
        settings,
        AiFeature.SCENE_TRANSLATION,
        default_max_output_tokens=1500,
        pool=pool,
        tracer=tracer,
    )
    return SceneTranslationService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_learning_task_generator(
    settings: AiSettings, tracer: AITracer, *, pool: ProviderPool | None = None
) -> LearningTaskService | None:
    """Build the configured learning-task generator, or ``None`` when off.

    ``None`` preserves the workflow's deterministic lesson-plan fallback.
    Four grammar tasks exceed the shared default output budget, so the
    default cap is raised here (the old SDK path had no explicit cap).
    """
    config = settings.feature(AiFeature.LEARNING_TASK)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    client, text_config = build_routed_client(
        "text",
        settings,
        AiFeature.LEARNING_TASK,
        default_max_output_tokens=4000,
        pool=pool,
        tracer=tracer,
    )
    return LearningTaskService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_ispy_clue_generator(
    settings: AiSettings, tracer: AITracer, *, pool: ProviderPool | None = None
) -> ISpyClueService | None:
    """Build the configured I-Spy clue generator, or ``None`` when off.

    ``None`` preserves the workflow's deterministic clue round.
    """
    config = settings.feature(AiFeature.ISPY_CLUE)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    client, text_config = build_routed_client(
        "text",
        settings,
        AiFeature.ISPY_CLUE,
        default_max_output_tokens=1500,
        pool=pool,
        tracer=tracer,
    )
    return ISpyClueService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_ispy_guess_generator(
    settings: AiSettings, tracer: AITracer, *, pool: ProviderPool | None = None
) -> ISpyGuessService | None:
    """Build the configured target-blind I-Spy evaluator, or ``None`` when off.

    ``None`` keeps the workflow's deterministic reflection tasks. A small
    output cap bounds the one short JSON verdict this call returns.
    """
    config = settings.feature(AiFeature.ISPY_GUESS)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    client, text_config = build_routed_client(
        "text",
        settings,
        AiFeature.ISPY_GUESS,
        default_max_output_tokens=500,
        pool=pool,
        tracer=tracer,
    )
    return ISpyGuessService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )
