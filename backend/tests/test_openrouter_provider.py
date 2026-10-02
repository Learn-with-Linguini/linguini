"""OpenRouter as a provider: settings, client construction and base URLs.

OpenRouter serves many vendors behind an OpenAI-compatible Responses API, so
these tests pin that the OpenAI adapters are reused with nothing but a
different host and key.
"""

import pytest

from app.ai import AiConfigurationError, AiFeature, AiProvider, load_ai_settings
from app.ai.openrouter import OPENROUTER_BASE_URL
from app.ai.registry import build_text_client, build_vision_client
from app.ai.text_model import TextModelConfig
from app.services.vision_model import VisionModelConfig


def settings(**env):
    """Demo mode: features may be configured one at a time."""
    return load_ai_settings(env=env)


def real_mode_env(**overrides):
    """A complete real-mode environment, so one gap is the only problem."""
    env = {
        "AI_MODE": "real",
        "AI_OPENAI_API_KEY": "sk-openai",
        "AI_GEMINI_API_KEY": "gemini-key",
        "AI_SCENE_ANALYSIS_MODEL": "gpt-scene",
        "AI_SCENE_ANALYSIS_PROVIDER": "openai",
    }
    env.update(overrides)
    return env


def test_openrouter_features_read_the_openrouter_key_and_model():
    loaded = settings(
        OPENROUTER_API_KEY="sk-or-test",
        AI_SCENE_TRANSLATION_PROVIDER="openrouter",
        AI_SCENE_TRANSLATION_MODEL="anthropic/claude-haiku-4.5",
    )

    config = loaded.feature(AiFeature.SCENE_TRANSLATION)
    assert config.provider is AiProvider.OPENROUTER
    assert config.model_name == "anthropic/claude-haiku-4.5"
    assert loaded.api_key_for(AiProvider.OPENROUTER) == "sk-or-test"
    assert loaded.is_configured(config)


def test_legacy_openrouter_model_variables_still_apply():
    loaded = settings(
        OPENROUTER_API_KEY="sk-or-test",
        ISPY_CLUE_PROVIDER="openrouter",
        OPENROUTER_ISPY_CLUE_MODEL="qwen/qwen3.8-flash",
    )

    assert loaded.feature(AiFeature.ISPY_CLUE).model_name == "qwen/qwen3.8-flash"


def test_real_mode_requires_the_openrouter_key():
    env = real_mode_env(
        AI_LEARNING_TASK_PROVIDER="openrouter",
        AI_LEARNING_TASK_MODEL="anthropic/claude-haiku-4.5",
    )

    with pytest.raises(AiConfigurationError) as error:
        load_ai_settings(env=env)

    assert "AI_OPENROUTER_API_KEY" in str(error.value)


def test_real_mode_accepts_openrouter_once_its_key_is_set():
    env = real_mode_env(
        AI_LEARNING_TASK_PROVIDER="openrouter",
        AI_LEARNING_TASK_MODEL="anthropic/claude-haiku-4.5",
        AI_OPENROUTER_API_KEY="sk-or-test",
    )

    loaded = load_ai_settings(env=env)

    assert loaded.feature(AiFeature.LEARNING_TASK).provider is AiProvider.OPENROUTER


def test_text_client_points_at_openrouter_with_its_own_key():
    loaded = settings(OPENROUTER_API_KEY="sk-or-test", OPENAI_API_KEY="sk-openai")

    client = build_text_client(
        AiProvider.OPENROUTER, loaded, TextModelConfig(model_name="qwen/qwen3.8-flash")
    )

    assert client._base_url == OPENROUTER_BASE_URL
    assert client._api_key == "sk-or-test"


def test_vision_client_points_at_openrouter():
    loaded = settings(OPENROUTER_API_KEY="sk-or-test")

    client = build_vision_client(
        AiProvider.OPENROUTER,
        loaded,
        VisionModelConfig(model_name="anthropic/claude-haiku-4.5"),
    )

    assert client._base_url == OPENROUTER_BASE_URL


def test_openai_provider_still_uses_the_openai_host():
    loaded = settings(OPENAI_API_KEY="sk-openai", OPENROUTER_API_KEY="sk-or-test")

    client = build_text_client(
        AiProvider.OPENAI, loaded, TextModelConfig(model_name="gpt-4.1-mini")
    )

    assert client._base_url == "https://api.openai.com/v1"
    assert client._api_key == "sk-openai"


def test_unsupported_providers_are_rejected():
    loaded = settings()

    with pytest.raises(ValueError):
        build_text_client(AiProvider.NONE, loaded, TextModelConfig(model_name="m"))
    with pytest.raises(ValueError):
        build_vision_client(AiProvider.NONE, loaded, VisionModelConfig(model_name="m"))
