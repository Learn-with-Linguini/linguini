"""Tests for AI settings loading: the TOML file plus environment settings."""

from pathlib import Path

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
from app.ai.settings import DEFAULT_AI_CONFIG_FILE
from tests.test_ai_config import example, write


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
    env = {
        "AI_MODE": "real",
        "AI_OPENROUTER_API_KEY": "sk-or",
        "AI_IMAGE_MODERATION_PROVIDER": "openai",
    }
    with pytest.raises(AiConfigurationError, match="imageModeration"):
        load_ai_settings(env=env)
    settings = load_ai_settings(env={**env, "AI_OPENAI_API_KEY": "sk-openai"})
    assert settings.image_moderation.provider is ImageModerationProvider.OPENAI
    assert settings.api_key_for(AiProvider.OPENAI) == "sk-openai"


def test_default_file_loads_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert DEFAULT_AI_CONFIG_FILE == Path(__file__).resolve().parents[1] / "ai.toml"
    settings = load_ai_settings(env={})
    assert settings.scene_translation.max_retries == 1
    assert settings.scene_translation.deployment_id == "translation-gpt-4o-mini"


def test_custom_file_sets_each_feature_provider_and_key(tmp_path):
    data = example()
    data["deployments"]["translation-gpt-4o-mini"].update(
        adapter="gemini", api="generateContent", model="gem-translate",
        credentials=["gemini"],
    )
    del data["deployments"]["translation-gpt-4o-mini"]["upstream_fallback"]
    data["deployments"]["guess-gpt-4-1-mini"].update(
        adapter="openai", model="gpt-guess", credentials=["openai"],
    )
    del data["deployments"]["guess-gpt-4-1-mini"]["upstream_fallback"]
    settings = load_ai_settings(
        env={
            "AI_MODE": "real",
            "AI_CONFIG_FILE": write(tmp_path, data),
            "AI_OPENROUTER_API_KEY": "sk-or",
            "AI_GEMINI_API_KEY": "gem-key",
            "AI_OPENAI_API_KEY": "sk-openai",
        }
    )
    assert settings.scene_translation.provider is AiProvider.GEMINI
    assert settings.scene_translation.model_name == "gem-translate"
    assert settings.secret_for(settings.scene_translation) == "gem-key"
    assert settings.ispy_guess.provider is AiProvider.OPENAI
    assert settings.secret_for(settings.ispy_guess) == "sk-openai"
    assert settings.learning_task.provider is AiProvider.OPENROUTER
    assert all(
        settings.is_configured(settings.feature(feature)) for feature in AiFeature
    )


def test_invalid_mode_raises_configuration_error():
    with pytest.raises(AiConfigurationError, match="AI_MODE"):
        load_ai_settings(env={"AI_MODE": "bogus"})


def test_real_mode_requires_a_secret_for_every_enabled_route():
    with pytest.raises(AiConfigurationError) as excinfo:
        load_ai_settings(env={"AI_MODE": "real", "AI_OPENAI_API_KEY": "sk-openai"})
    message = str(excinfo.value)
    for feature in AiFeature:
        assert feature.value in message
    assert "AI_OPENROUTER_API_KEY" in message
    assert "sk-openai" not in message


def test_demo_mode_with_no_keys_uses_deterministic_fallback():
    settings = load_ai_settings(env={"AI_MODE": "demo"})
    assert settings.mode is AiMode.DEMO
    for feature in AiFeature:
        config = settings.feature(feature)
        assert settings.is_configured(config) is False


def test_default_file_holds_the_measured_defaults():
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
    assert learning.max_output_tokens == 4000

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


def test_removed_environment_variables_have_no_effect():
    removed = {
        "AI_SCENE_TRANSLATION_PROVIDER": "openai",
        "AI_SCENE_TRANSLATION_MODEL": "other/model",
        "AI_LEARNING_TASK_MAX_OUTPUT_TOKENS": "10",
        "TRANSLATION_PROVIDER": "gemini",
        "OPENROUTER_TRANSLATION_MODEL": "legacy/model",
        "OPENROUTER_API_KEY": "sk-legacy",
        "AI_API_KEY": "general",
        "VISION_MODEL_NAME": "gpt-legacy",
        "LANGFUSE_PUBLIC_KEY": "pk-legacy",
        "LANGFUSE_TRACING_ENABLED": "true",
    }
    assert load_ai_settings(env=removed) == load_ai_settings(env={})


def test_settings_are_plain_frozen_models_without_clients():
    settings = load_ai_settings(env={})
    assert isinstance(settings, AiSettings)
    assert isinstance(settings.scene_analysis, FeatureModelConfig)
    for value in vars(settings).values():
        assert not callable(value)
    with pytest.raises(ValidationError):
        settings.scene_analysis.model_name = "changed"
    assert settings.api_key_for(AiProvider.OPENAI) == ""
    assert settings.api_key_for(AiProvider.NONE) == ""


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


def test_observability_invalid_values_raise_configuration_error():
    with pytest.raises(
        AiConfigurationError, match="AI_OBSERVABILITY_ENABLED"
    ):
        load_ai_settings(env={"AI_OBSERVABILITY_ENABLED": "maybe"})
    with pytest.raises(AiConfigurationError, match="'Bad Env'"):
        load_ai_settings(env={"AI_OBSERVABILITY_ENVIRONMENT": "Bad Env"})
    with pytest.raises(AiConfigurationError, match="langfuse-prod"):
        load_ai_settings(env={"AI_OBSERVABILITY_ENVIRONMENT": "langfuse-prod"})


def test_real_mode_requires_langfuse_keys_when_observability_enabled():
    with pytest.raises(AiConfigurationError) as excinfo:
        load_ai_settings(
            env={
                "AI_MODE": "real",
                "AI_OPENROUTER_API_KEY": "k",
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
