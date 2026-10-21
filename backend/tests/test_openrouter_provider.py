"""OpenRouter as a provider: settings, client construction and base URLs.

OpenRouter serves many vendors behind an OpenAI-compatible Responses API, so
these tests pin that the OpenAI adapters are reused with nothing but a
different host and key.
"""

import pytest

from app.ai import AiConfigurationError, AiFeature, AiProvider, load_ai_settings
from app.ai.adapters.openrouter import OPENROUTER_BASE_URL
from app.ai.contracts import VisionModelConfig
from app.ai.contracts.text import TextModelConfig
from app.ai.registry import build_text_client, build_vision_client


def settings(**env):
    return load_ai_settings(env=env)


def test_openrouter_features_read_the_openrouter_key_and_model():
    loaded = settings(AI_OPENROUTER_API_KEY="sk-or-test")

    config = loaded.feature(AiFeature.SCENE_ANALYSIS)
    assert config.provider is AiProvider.OPENROUTER
    assert config.model_name == "anthropic/claude-haiku-4.5"
    assert loaded.api_key_for(AiProvider.OPENROUTER) == "sk-or-test"
    assert loaded.is_configured(config)


def test_real_mode_requires_the_openrouter_key():
    with pytest.raises(AiConfigurationError) as error:
        load_ai_settings(env={"AI_MODE": "real", "AI_OPENAI_API_KEY": "sk-openai"})

    assert "AI_OPENROUTER_API_KEY" in str(error.value)


def test_real_mode_accepts_openrouter_once_its_key_is_set():
    loaded = load_ai_settings(env={"AI_MODE": "real", "AI_OPENROUTER_API_KEY": "sk-or-test"})

    assert loaded.feature(AiFeature.LEARNING_TASK).provider is AiProvider.OPENROUTER


def test_text_client_points_at_openrouter_with_its_own_key():
    loaded = settings(AI_OPENROUTER_API_KEY="sk-or-test", AI_OPENAI_API_KEY="sk-openai")

    client = build_text_client(
        AiProvider.OPENROUTER, loaded, TextModelConfig(model_name="qwen/qwen3.8-flash")
    )

    assert client._base_url == OPENROUTER_BASE_URL
    assert client._api_key == "sk-or-test"


def test_vision_client_points_at_openrouter():
    loaded = settings(AI_OPENROUTER_API_KEY="sk-or-test")

    client = build_vision_client(
        AiProvider.OPENROUTER,
        loaded,
        VisionModelConfig(model_name="anthropic/claude-haiku-4.5"),
    )

    assert client._base_url == OPENROUTER_BASE_URL


def test_openai_provider_still_uses_the_openai_host():
    loaded = settings(AI_OPENAI_API_KEY="sk-openai", AI_OPENROUTER_API_KEY="sk-or-test")

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
