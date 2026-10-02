"""Tests for centralized AI settings loading (pure env-dict driven)."""

import pytest
from pydantic import ValidationError

from app.ai import (
    AiConfigurationError,
    AiFeature,
    AiMode,
    AiProvider,
    AiSettings,
    FeatureModelConfig,
    ImageModerationProvider,
    ObjectGroundingProvider,
    load_ai_settings,
)


def test_object_grounding_is_off_by_default_and_can_use_grounding_dino():
    assert load_ai_settings(env={}).object_grounding.provider is ObjectGroundingProvider.NONE

    settings = load_ai_settings(
        env={
            "AI_OBJECT_GROUNDING_PROVIDER": "groundingDino",
            "AI_OBJECT_GROUNDING_MODEL": "my-detector",
            "AI_OBJECT_GROUNDING_THRESHOLD": "0.6",
        }
    )

    assert settings.object_grounding.provider is ObjectGroundingProvider.GROUNDING_DINO
    assert settings.object_grounding.model_name == "my-detector"
    assert settings.object_grounding.threshold == 0.6


def test_object_grounding_batch_and_resize_limits_parse_as_positive_ints():
    settings = load_ai_settings(
        env={
            "AI_OBJECT_GROUNDING_MAX_LABELS": "20",
            "AI_OBJECT_GROUNDING_MAX_IMAGE_SIDE": "512",
        }
    )
    assert settings.object_grounding.max_labels == 20
    assert settings.object_grounding.max_image_side == 512

    with pytest.raises(AiConfigurationError, match="AI_OBJECT_GROUNDING_MAX_LABELS"):
        load_ai_settings(env={"AI_OBJECT_GROUNDING_MAX_LABELS": "many"})
    with pytest.raises(AiConfigurationError, match="AI_OBJECT_GROUNDING_MAX_LABELS"):
        load_ai_settings(env={"AI_OBJECT_GROUNDING_MAX_LABELS": "0"})
    with pytest.raises(
        AiConfigurationError, match="AI_OBJECT_GROUNDING_MAX_IMAGE_SIDE"
    ):
        load_ai_settings(env={"AI_OBJECT_GROUNDING_MAX_IMAGE_SIDE": "-4"})


def test_image_moderation_is_off_by_default_and_parses_openai_config():
    assert load_ai_settings(env={}).image_moderation.provider is ImageModerationProvider.NONE

    settings = load_ai_settings(
        env={
            "AI_OPENAI_API_KEY": "sk-openai",
            "AI_IMAGE_MODERATION_PROVIDER": "openai",
            "AI_IMAGE_MODERATION_MODEL": "custom-moderation",
            "AI_IMAGE_MODERATION_TIMEOUT_SECONDS": "10",
        }
    )
    assert settings.image_moderation.provider is ImageModerationProvider.OPENAI
    assert settings.image_moderation.model_name == "custom-moderation"
    assert settings.image_moderation.timeout_seconds == 10

    defaulted = load_ai_settings(env={"AI_IMAGE_MODERATION_PROVIDER": "openai"})
    assert defaulted.image_moderation.model_name == "omni-moderation-latest"
    assert defaulted.image_moderation.timeout_seconds == 30

    with pytest.raises(AiConfigurationError, match="image moderation provider"):
        load_ai_settings(env={"AI_IMAGE_MODERATION_PROVIDER": "gemini"})
    with pytest.raises(
        AiConfigurationError, match="AI_IMAGE_MODERATION_TIMEOUT_SECONDS"
    ):
        load_ai_settings(env={"AI_IMAGE_MODERATION_TIMEOUT_SECONDS": "soon"})
    with pytest.raises(
        AiConfigurationError, match="AI_IMAGE_MODERATION_TIMEOUT_SECONDS"
    ):
        load_ai_settings(env={"AI_IMAGE_MODERATION_TIMEOUT_SECONDS": "0"})


def test_real_mode_requires_openai_key_for_openai_moderation():
    with pytest.raises(AiConfigurationError, match="imageModeration"):
        load_ai_settings(
            env={
                "AI_MODE": "real",
                "AI_GEMINI_API_KEY": "gem-key",
                "AI_SCENE_ANALYSIS_PROVIDER": "gemini",
                "AI_SCENE_ANALYSIS_MODEL": "m",
                "AI_SCENE_TRANSLATION_PROVIDER": "gemini",
                "AI_SCENE_TRANSLATION_MODEL": "m",
                "AI_LEARNING_TASK_PROVIDER": "none",
                "AI_ISPY_CLUE_PROVIDER": "none",
                "AI_ISPY_GUESS_PROVIDER": "none",
                "AI_IMAGE_MODERATION_PROVIDER": "openai",
            }
        )
    # With the OpenAI key present the same configuration loads cleanly.
    settings = load_ai_settings(
        env={
            "AI_MODE": "real",
            "AI_GEMINI_API_KEY": "gem-key",
            "AI_OPENAI_API_KEY": "sk-openai",
            "AI_OPENROUTER_API_KEY": "sk-or",
            "AI_SCENE_ANALYSIS_PROVIDER": "gemini",
            "AI_SCENE_ANALYSIS_MODEL": "m",
            "AI_SCENE_TRANSLATION_PROVIDER": "gemini",
            "AI_SCENE_TRANSLATION_MODEL": "m",
            "AI_LEARNING_TASK_MODEL": "m",
            "AI_ISPY_CLUE_MODEL": "m",
            "AI_ISPY_GUESS_MODEL": "m",
            "AI_IMAGE_MODERATION_PROVIDER": "openai",
        }
    )
    assert settings.image_moderation.provider is ImageModerationProvider.OPENAI


def test_translation_retries_once_by_default_and_respects_explicit_zero():
    assert load_ai_settings(env={}).scene_translation.max_retries == 1
    assert load_ai_settings(env={
        "AI_SCENE_TRANSLATION_MAX_RETRIES": "0"
    }).scene_translation.max_retries == 0


def test_openai_configuration_all_features():
    settings = load_ai_settings(
        env={
            "AI_MODE": "real",
            "AI_OPENAI_API_KEY": "sk-openai",
            "AI_SCENE_ANALYSIS_PROVIDER": "openai",
            "AI_SCENE_ANALYSIS_MODEL": "gpt-scene",
            "AI_SCENE_ANALYSIS_TIMEOUT_SECONDS": "30",
            "AI_SCENE_ANALYSIS_MAX_OUTPUT_TOKENS": "1000",
            "AI_SCENE_ANALYSIS_MAX_RETRIES": "2",
            "AI_SCENE_TRANSLATION_PROVIDER": "openai",
            "AI_SCENE_TRANSLATION_MODEL": "gpt-translate",
            "AI_SCENE_TRANSLATION_TIMEOUT_SECONDS": "45",
            "AI_LEARNING_TASK_PROVIDER": "openai",
            "AI_LEARNING_TASK_MODEL": "gpt-learn",
            "AI_LEARNING_TASK_TIMEOUT_SECONDS": "50",
            "AI_ISPY_CLUE_PROVIDER": "openai",
            "AI_ISPY_CLUE_MODEL": "gpt-clue",
            "AI_ISPY_CLUE_TIMEOUT_SECONDS": "25",
            "AI_ISPY_GUESS_PROVIDER": "openai",
            "AI_ISPY_GUESS_MODEL": "gpt-guess",
            "AI_ISPY_GUESS_TIMEOUT_SECONDS": "15",
        }
    )
    assert settings.mode is AiMode.REAL
    assert settings.openai_api_key == "sk-openai"
    for feature, model, timeout in [
        (AiFeature.SCENE_ANALYSIS, "gpt-scene", 30),
        (AiFeature.SCENE_TRANSLATION, "gpt-translate", 45),
        (AiFeature.LEARNING_TASK, "gpt-learn", 50),
        (AiFeature.ISPY_CLUE, "gpt-clue", 25),
        (AiFeature.ISPY_GUESS, "gpt-guess", 15),
    ]:
        config = settings.feature(feature)
        assert config.provider is AiProvider.OPENAI
        assert config.model_name == model
        assert config.timeout_seconds == timeout
        assert settings.is_configured(config)
    scene = settings.scene_analysis
    assert scene.max_output_tokens == 1000
    assert scene.max_retries == 2


def test_gemini_configuration_for_supported_features():
    settings = load_ai_settings(
        env={
            "AI_GEMINI_API_KEY": "gem-key",
            "AI_SCENE_ANALYSIS_PROVIDER": "gemini",
            "AI_SCENE_ANALYSIS_MODEL": "gem-scene",
            "AI_SCENE_TRANSLATION_PROVIDER": "gemini",
            "AI_SCENE_TRANSLATION_MODEL": "gem-translate",
            "AI_LEARNING_TASK_PROVIDER": "gemini",
            "AI_LEARNING_TASK_MODEL": "gem-learn",
        }
    )
    assert settings.gemini_api_key == "gem-key"
    for feature, model in [
        (AiFeature.SCENE_ANALYSIS, "gem-scene"),
        (AiFeature.SCENE_TRANSLATION, "gem-translate"),
        (AiFeature.LEARNING_TASK, "gem-learn"),
    ]:
        config = settings.feature(feature)
        assert config.provider is AiProvider.GEMINI
        assert config.model_name == model
        assert settings.is_configured(config)


def test_per_feature_mixed_providers():
    settings = load_ai_settings(
        env={
            "AI_OPENAI_API_KEY": "sk-openai",
            "AI_GEMINI_API_KEY": "gem-key",
            "AI_SCENE_ANALYSIS_PROVIDER": "gemini",
            "AI_SCENE_ANALYSIS_MODEL": "gem-scene",
            "AI_SCENE_TRANSLATION_PROVIDER": "openai",
            "AI_SCENE_TRANSLATION_MODEL": "gpt-translate",
            "AI_LEARNING_TASK_PROVIDER": "gemini",
            "AI_LEARNING_TASK_MODEL": "gem-learn",
            "AI_ISPY_CLUE_PROVIDER": "openai",
            "AI_ISPY_CLUE_MODEL": "gpt-clue",
            "AI_ISPY_GUESS_PROVIDER": "openai",
            "AI_ISPY_GUESS_MODEL": "gpt-guess",
        }
    )
    assert settings.scene_analysis.provider is AiProvider.GEMINI
    assert settings.scene_translation.provider is AiProvider.OPENAI
    assert settings.learning_task.provider is AiProvider.GEMINI
    assert settings.ispy_clue.provider is AiProvider.OPENAI
    assert settings.ispy_guess.provider is AiProvider.OPENAI
    assert all(
        settings.is_configured(settings.feature(feature)) for feature in AiFeature
    )


def test_invalid_provider_mode_and_timeout_raise_configuration_error():
    with pytest.raises(AiConfigurationError, match="sceneAnalysis.*anthropic"):
        load_ai_settings(env={"AI_SCENE_ANALYSIS_PROVIDER": "anthropic"})
    with pytest.raises(AiConfigurationError, match="AI_MODE"):
        load_ai_settings(env={"AI_MODE": "bogus"})
    with pytest.raises(AiConfigurationError, match="sceneAnalysis"):
        load_ai_settings(env={"AI_SCENE_ANALYSIS_TIMEOUT_SECONDS": "soon"})
    # Non-integer timeouts are rejected even though they parse as floats:
    # provider constructors take int seconds.
    with pytest.raises(AiConfigurationError, match="sceneAnalysis"):
        load_ai_settings(env={"AI_SCENE_ANALYSIS_TIMEOUT_SECONDS": "60.5"})


def test_real_mode_requires_key_and_model_for_enabled_features():
    with pytest.raises(AiConfigurationError) as excinfo:
        load_ai_settings(env={"AI_MODE": "real"})
    message = str(excinfo.value)
    # Default providers: gemini for analysis/translation, openai elsewhere —
    # every feature lacks its provider key.
    for feature in AiFeature:
        assert feature.value in message

    # Gemini scene provider with key set but empty model still fails.
    with pytest.raises(AiConfigurationError, match="sceneAnalysis"):
        load_ai_settings(
            env={
                "AI_MODE": "real",
                "AI_GEMINI_API_KEY": "gem-key",
                "AI_OPENAI_API_KEY": "sk-openai",
                "AI_SCENE_TRANSLATION_PROVIDER": "none",
                "AI_LEARNING_TASK_PROVIDER": "none",
                "AI_ISPY_CLUE_PROVIDER": "none",
                "AI_ISPY_GUESS_PROVIDER": "none",
            }
        )


def test_demo_mode_with_no_keys_uses_deterministic_fallback():
    settings = load_ai_settings(env={"AI_MODE": "demo"})
    assert settings.mode is AiMode.DEMO
    for feature in AiFeature:
        config = settings.feature(feature)
        assert settings.is_configured(config) is False


def test_empty_env_reproduces_the_measured_defaults():
    """Defaults are the models chosen in MODEL_COMPARISON.md."""
    settings = load_ai_settings(env={})
    assert settings.mode is AiMode.DEMO

    scene = settings.scene_analysis
    assert scene.provider is AiProvider.OPENROUTER
    assert scene.model_name == "anthropic/claude-haiku-4.5"
    assert scene.timeout_seconds == 120

    translation = settings.scene_translation
    assert translation.provider is AiProvider.OPENROUTER
    assert translation.model_name == "openai/gpt-4o-mini"
    assert translation.timeout_seconds == 60

    learning = settings.learning_task
    assert learning.provider is AiProvider.OPENROUTER
    assert learning.model_name == "openai/gpt-5.4-mini"
    assert learning.timeout_seconds == 60
    assert learning.max_retries == 1

    clue = settings.ispy_clue
    assert clue.provider is AiProvider.OPENROUTER
    assert clue.model_name == "google/gemini-3.1-flash-lite"
    assert clue.max_retries == 1

    guess = settings.ispy_guess
    assert guess.provider is AiProvider.OPENROUTER
    assert guess.model_name == "openai/gpt-4.1-mini"
    assert guess.max_retries == 0

    for config in (clue, guess):
        assert config.timeout_seconds == 60
        assert config.max_output_tokens is None


def test_legacy_aliases_produce_identical_settings():
    legacy_env = {
        "OPENAI_API_KEY": "sk-openai",
        "GEMINI_API_KEY": "gem-key",
        "SCENE_ANALYSIS_PROVIDER": "openai",
        "SCENE_ANALYSIS_TIMEOUT_SECONDS": "90",
        "OPENAI_SCENE_MODEL": "gpt-scene",
        "TRANSLATION_PROVIDER": "gemini",
        "TRANSLATION_TIMEOUT_SECONDS": "45",
        "GEMINI_TRANSLATION_MODEL": "gem-translate",
        "LEARNING_TASK_PROVIDER": "openai",
        "LEARNING_TASK_TIMEOUT_SECONDS": "30",
        "OPENAI_LEARNING_TASK_MODEL": "gpt-learn",
        "ISPY_CLUE_PROVIDER": "openai",
        "ISPY_CLUE_TIMEOUT_SECONDS": "20",
        "OPENAI_ISPY_CLUE_MODEL": "gpt-clue",
        "ISPY_GUESS_PROVIDER": "none",
        "ISPY_GUESS_TIMEOUT_SECONDS": "10",
        "OPENAI_ISPY_GUESS_MODEL": "gpt-guess",
    }
    canonical_env = {
        "AI_OPENAI_API_KEY": "sk-openai",
        "AI_GEMINI_API_KEY": "gem-key",
        "AI_SCENE_ANALYSIS_PROVIDER": "openai",
        "AI_SCENE_ANALYSIS_TIMEOUT_SECONDS": "90",
        "AI_SCENE_ANALYSIS_MODEL": "gpt-scene",
        "AI_SCENE_TRANSLATION_PROVIDER": "gemini",
        "AI_SCENE_TRANSLATION_TIMEOUT_SECONDS": "45",
        "AI_SCENE_TRANSLATION_MODEL": "gem-translate",
        "AI_LEARNING_TASK_PROVIDER": "openai",
        "AI_LEARNING_TASK_TIMEOUT_SECONDS": "30",
        "AI_LEARNING_TASK_MODEL": "gpt-learn",
        "AI_ISPY_CLUE_PROVIDER": "openai",
        "AI_ISPY_CLUE_TIMEOUT_SECONDS": "20",
        "AI_ISPY_CLUE_MODEL": "gpt-clue",
        "AI_ISPY_GUESS_PROVIDER": "none",
        "AI_ISPY_GUESS_TIMEOUT_SECONDS": "10",
        # No AI_ISPY_GUESS_MODEL: the legacy var is ignored when the provider
        # is "none", so the canonical equivalent omits it too.
    }
    assert load_ai_settings(env=legacy_env) == load_ai_settings(env=canonical_env)

    # Canonical wins when both are present.
    both = dict(legacy_env)
    both["AI_SCENE_ANALYSIS_MODEL"] = "canonical-model"
    settings = load_ai_settings(env=both)
    assert settings.scene_analysis.model_name == "canonical-model"


def test_settings_are_plain_frozen_models_without_clients():
    settings = load_ai_settings(env={})
    assert isinstance(settings, AiSettings)
    assert isinstance(settings.scene_analysis, FeatureModelConfig)
    for value in vars(settings).values():
        assert not callable(value)
    with pytest.raises(ValidationError):
        settings.scene_analysis.model_name = "changed"
    # general_api_key is never substituted for a provider key.
    keyed = load_ai_settings(env={"AI_API_KEY": "general"})
    assert keyed.api_key_for(AiProvider.OPENAI) == ""
    assert keyed.api_key_for(AiProvider.NONE) == ""


def test_observability_defaults_and_canonical_names():
    defaults = load_ai_settings(env={}).observability
    assert defaults.enabled is False
    assert defaults.base_url == "https://cloud.langfuse.com"
    assert defaults.public_key == ""
    assert defaults.secret_key == ""
    assert defaults.environment == "development"
    assert defaults.capture_content is False

    settings = load_ai_settings(
        env={
            "AI_OBSERVABILITY_ENABLED": "true",
            "AI_OBSERVABILITY_BASE_URL": "https://lf.example.com",
            "AI_OBSERVABILITY_PUBLIC_KEY": "pk",
            "AI_OBSERVABILITY_SECRET_KEY": "sk",
            "AI_OBSERVABILITY_ENVIRONMENT": "staging",
            "AI_OBSERVABILITY_CAPTURE_CONTENT": "on",
        }
    ).observability
    assert settings.enabled is True
    assert settings.base_url == "https://lf.example.com"
    assert settings.public_key == "pk"
    assert settings.secret_key == "sk"
    assert settings.environment == "staging"
    assert settings.capture_content is True


def test_observability_langfuse_aliases_and_canonical_precedence():
    settings = load_ai_settings(
        env={
            "LANGFUSE_TRACING_ENABLED": "yes",
            "LANGFUSE_PUBLIC_KEY": "pk-alias",
            "LANGFUSE_SECRET_KEY": "sk-alias",
            "LANGFUSE_HOST": "https://host.example.com",
            "LANGFUSE_TRACING_ENVIRONMENT": "prod",
            # Canonical wins when both are present.
            "AI_OBSERVABILITY_PUBLIC_KEY": "pk-canonical",
            "AI_OBSERVABILITY_BASE_URL": "https://canonical.example.com",
        }
    ).observability
    assert settings.enabled is True
    assert settings.public_key == "pk-canonical"
    assert settings.secret_key == "sk-alias"
    assert settings.base_url == "https://canonical.example.com"
    assert settings.environment == "prod"


def test_observability_invalid_values_raise_configuration_error():
    with pytest.raises(
        AiConfigurationError, match="AI_OBSERVABILITY_ENABLED"
    ):
        load_ai_settings(env={"AI_OBSERVABILITY_ENABLED": "maybe"})
    with pytest.raises(AiConfigurationError, match="'maybe'"):
        load_ai_settings(env={"LANGFUSE_TRACING_ENABLED": "maybe"})
    with pytest.raises(AiConfigurationError, match="'Bad Env'"):
        load_ai_settings(env={"AI_OBSERVABILITY_ENVIRONMENT": "Bad Env"})
    with pytest.raises(AiConfigurationError, match="langfuse-prod"):
        load_ai_settings(env={"AI_OBSERVABILITY_ENVIRONMENT": "langfuse-prod"})


def test_real_mode_requires_langfuse_keys_when_observability_enabled():
    with pytest.raises(AiConfigurationError) as excinfo:
        load_ai_settings(
            env={
                "AI_MODE": "real",
                "AI_OPENAI_API_KEY": "k",
                "AI_GEMINI_API_KEY": "k",
                "AI_SCENE_ANALYSIS_MODEL": "m",
                "AI_SCENE_TRANSLATION_MODEL": "m",
                "AI_LEARNING_TASK_MODEL": "m",
                "AI_ISPY_CLUE_MODEL": "m",
                "AI_ISPY_GUESS_MODEL": "m",
                "AI_OBSERVABILITY_ENABLED": "true",
                "AI_OBSERVABILITY_PUBLIC_KEY": "pk",
            }
        )
    message = str(excinfo.value)
    assert "observability" in message
    assert "AI_OBSERVABILITY_SECRET_KEY" in message

    # Demo mode never fails on missing Langfuse keys.
    demo = load_ai_settings(
        env={"AI_MODE": "demo", "AI_OBSERVABILITY_ENABLED": "true"}
    )
    assert demo.observability.enabled is True
    assert demo.observability.secret_key == ""
