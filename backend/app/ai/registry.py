"""Provider-neutral client/service construction from centralized AI settings.

Reads only ``AiSettings`` — providers and models are never chosen anywhere
else. Returns ``None`` for features configured off so callers keep their
deterministic fallbacks.
"""

from __future__ import annotations

from app.ai.adapters.gemini import GeminiTextClient, GeminiVisionClient
from app.ai.adapters.openai import OpenAITextClient, OpenAIVisionClient
from app.ai.adapters.openrouter import OpenRouterTextClient, OpenRouterVisionClient
from app.ai.contracts import VisionModelClient, VisionModelConfig
from app.ai.contracts.text import TextModelClient, TextModelConfig
from app.ai.features.ispy_clues import ISpyClueService
from app.ai.features.ispy_guess import ISpyGuessService
from app.ai.features.learning_tasks import LearningTaskService
from app.ai.features.moderation import ImageModerator, OpenAIImageModerator
from app.ai.features.object_grounding import GroundingDinoObjectGrounder, ObjectGrounder
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.features.translation import SceneTranslationService
from app.ai.observability import AITracer
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
) -> TextModelClient:
    key = settings.api_key_for(provider) if api_key is None else api_key
    if provider is AiProvider.OPENAI:
        return OpenAITextClient(key, config)
    if provider is AiProvider.GEMINI:
        return GeminiTextClient(key, config)
    if provider is AiProvider.OPENROUTER:
        return OpenRouterTextClient(key, config)
    raise ValueError(f"unsupported text provider {provider!r}")


def build_vision_client(
    provider: AiProvider,
    settings: AiSettings,
    config: VisionModelConfig,
    *,
    api_key: str | None = None,
) -> VisionModelClient:
    key = settings.api_key_for(provider) if api_key is None else api_key
    if provider is AiProvider.OPENAI:
        return OpenAIVisionClient(key, config)
    if provider is AiProvider.GEMINI:
        return GeminiVisionClient(key, config)
    if provider is AiProvider.OPENROUTER:
        return OpenRouterVisionClient(key, config)
    raise ValueError(f"unsupported vision provider {provider!r}")


def build_uploaded_scene_analyzer(
    settings: AiSettings,
    storage: ImageStorage,
    tracer: AITracer,
    object_grounder: ObjectGrounder | None = None,
    image_moderator: ImageModerator | None = None,
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
        vision_config = VisionModelConfig(
            model_name=scene_config.model_name,
            timeout_seconds=scene_config.timeout_seconds,
            max_output_tokens=scene_config.max_output_tokens or 1500,
            max_retries=min(scene_config.max_retries, 1),
            temperature=scene_config.temperature,
        )
        return UploadedSceneAnalyzer(
            storage,
            build_vision_client(
                scene_config.provider,
                settings,
                vision_config,
                api_key=settings.secret_for(scene_config),
            ),
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
    settings: AiSettings, tracer: AITracer
) -> SceneTranslationService | None:
    """Build the configured scene translator, or ``None`` when turned off.

    ``None`` preserves the workflow's deterministic offline fallback.
    """
    config = settings.feature(AiFeature.SCENE_TRANSLATION)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    text_config = TextModelConfig(
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens or 1500,
        max_retries=min(config.max_retries, 1),
        temperature=config.temperature,
    )
    client = build_text_client(
        config.provider, settings, text_config, api_key=settings.secret_for(config)
    )
    return SceneTranslationService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_learning_task_generator(
    settings: AiSettings, tracer: AITracer
) -> LearningTaskService | None:
    """Build the configured learning-task generator, or ``None`` when off.

    ``None`` preserves the workflow's deterministic lesson-plan fallback.
    Four grammar tasks exceed the shared default output budget, so the
    default cap is raised here (the old SDK path had no explicit cap).
    """
    config = settings.feature(AiFeature.LEARNING_TASK)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    text_config = TextModelConfig(
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens or 4000,
        max_retries=min(config.max_retries, 1),
        temperature=config.temperature,
    )
    client = build_text_client(
        config.provider, settings, text_config, api_key=settings.secret_for(config)
    )
    return LearningTaskService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_ispy_clue_generator(
    settings: AiSettings, tracer: AITracer
) -> ISpyClueService | None:
    """Build the configured I-Spy clue generator, or ``None`` when off.

    ``None`` preserves the workflow's deterministic clue round.
    """
    config = settings.feature(AiFeature.ISPY_CLUE)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    text_config = TextModelConfig(
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens or 1500,
        max_retries=min(config.max_retries, 1),
        temperature=config.temperature,
    )
    client = build_text_client(
        config.provider, settings, text_config, api_key=settings.secret_for(config)
    )
    return ISpyClueService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )


def build_ispy_guess_generator(
    settings: AiSettings, tracer: AITracer
) -> ISpyGuessService | None:
    """Build the configured target-blind I-Spy evaluator, or ``None`` when off.

    ``None`` keeps the workflow's deterministic reflection tasks. A small
    output cap bounds the one short JSON verdict this call returns.
    """
    config = settings.feature(AiFeature.ISPY_GUESS)
    if config.provider is AiProvider.NONE or not settings.is_configured(config):
        return None
    text_config = TextModelConfig(
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens or 500,
        max_retries=min(config.max_retries, 1),
        temperature=config.temperature,
    )
    client = build_text_client(
        config.provider, settings, text_config, api_key=settings.secret_for(config)
    )
    return ISpyGuessService(
        client, text_config, tracer=tracer, provider=config.provider.value
    )
