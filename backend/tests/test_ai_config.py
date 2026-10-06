"""TOML AI configuration: validation, compatibility mapping and precedence."""

import copy
import json
import logging
import socket
import tomllib
from pathlib import Path

import pytest

from app.ai import registry
from app.ai.config import (
    AiConfigurationError,
    ApiType,
    Capability,
    SelectionPolicy,
    parse_ai_config,
    resolve_credential_secrets,
)
from app.ai.contracts.text import TextModelRequest, TextModelResponse
from app.ai.observability import build_tracer
from app.ai.settings import AiFeature, AiProvider, load_ai_settings

EXAMPLE = Path(__file__).resolve().parents[1] / "ai.example.toml"
KEY = "sk-or-test-secret"
TRANSLATION = "translation-gpt-4o-mini"


def example() -> dict:
    return copy.deepcopy(tomllib.loads(EXAMPLE.read_text()))


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    return "{" + ", ".join(f"{k} = {_value(v)}" for k, v in value.items()) + "}"


def write(tmp_path: Path, data: dict) -> str:
    lines = []
    for section, entries in data.items():
        for name, table in entries.items():
            lines.append(f"[{section}.{name}]")
            lines.extend(f"{key} = {_value(value)}" for key, value in table.items())
    path = tmp_path / "ai.toml"
    path.write_text("\n".join(lines))
    return str(path)


def comparable(config):
    return (
        config.provider,
        config.model_name,
        config.timeout_seconds,
        config.max_output_tokens,
        config.max_retries,
        config.temperature,
    )


def test_example_file_matches_the_environment_defaults():
    env = {"AI_OPENROUTER_API_KEY": KEY}
    from_env = load_ai_settings(env)
    from_file = load_ai_settings({**env, "AI_CONFIG_FILE": str(EXAMPLE)})

    for feature in AiFeature:
        assert comparable(from_file.feature(feature)) == comparable(from_env.feature(feature))
        assert from_file.is_configured(from_file.feature(feature))
        assert from_file.secret_for(from_file.feature(feature)) == KEY
    route = from_file.ai_config.routes[AiFeature.SCENE_TRANSLATION]
    assert route.policy is SelectionPolicy.PRIORITY
    assert (route.deadline_seconds, route.max_model_calls) == (120, 2)
    assert from_file.scene_translation.deployment_id == TRANSLATION


def test_environment_maps_to_one_deployment_per_feature():
    config = load_ai_settings({}).ai_config

    for feature in AiFeature:
        route = config.routes[feature]
        assert route.enabled and route.deployments == (feature.value,)
        deployment = config.deployments[feature.value]
        assert deployment.adapter is AiProvider.OPENROUTER
        assert deployment.api is ApiType.RESPONSES
        assert deployment.credentials == ("openrouter",)
    assert Capability.VISION in config.deployments["sceneAnalysis"].capabilities
    assert config.credentials["openrouter"].env == ("AI_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    translation = config.routes[AiFeature.SCENE_TRANSLATION]
    assert (translation.deadline_seconds, translation.max_model_calls) == (120, 2)
    guess = config.routes[AiFeature.ISPY_GUESS]
    assert (guess.deadline_seconds, guess.max_model_calls) == (60, 1)


def test_environment_mapping_follows_provider_choice():
    settings = load_ai_settings(
        {"AI_ISPY_CLUE_PROVIDER": "none", "AI_SCENE_TRANSLATION_PROVIDER": "gemini"}
    )
    config = settings.ai_config

    assert not config.routes[AiFeature.ISPY_CLUE].enabled
    assert config.primary_deployment(AiFeature.ISPY_CLUE) is None
    deployment = config.deployments["sceneTranslation"]
    assert deployment.api is ApiType.GENERATE_CONTENT
    assert deployment.credentials == ("gemini",)
    assert settings.scene_translation.credential_id == "gemini"


def test_toml_wins_and_ignored_variables_are_logged_by_name(caplog):
    env = {
        "AI_OPENROUTER_API_KEY": KEY,
        "AI_CONFIG_FILE": str(EXAMPLE),
        "AI_SCENE_TRANSLATION_MODEL": "other/model",
        "OPENROUTER_TRANSLATION_MODEL": "legacy/model",
        "AI_LEARNING_TASK_MAX_OUTPUT_TOKENS": "",
    }
    with caplog.at_level(logging.WARNING, logger="app.ai.settings"):
        settings = load_ai_settings(env)

    assert settings.scene_translation.model_name == "openai/gpt-4o-mini"
    assert "AI_SCENE_TRANSLATION_MODEL" in caplog.text
    assert "OPENROUTER_TRANSLATION_MODEL" in caplog.text
    assert "AI_LEARNING_TASK_MAX_OUTPUT_TOKENS" not in caplog.text
    assert "other/model" not in caplog.text and KEY not in caplog.text


def test_no_warning_without_overridden_variables(caplog):
    with caplog.at_level(logging.WARNING, logger="app.ai.settings"):
        load_ai_settings({"AI_CONFIG_FILE": str(EXAMPLE)})
    assert caplog.text == ""


def test_route_uses_first_eligible_credential_with_a_secret(tmp_path, monkeypatch):
    data = example()
    data["credentials"]["team"] = {
        "adapter": "openrouter",
        "env": ["TEAM_OPENROUTER_KEY"],
        "quota_group": "team",
        "billing_group": "team-billing",
    }
    deployment = data["deployments"][TRANSLATION]
    deployment["credentials"] = ["openrouter", "team"]
    deployment["defaults"]["temperature"] = 0.3
    settings = load_ai_settings(
        {"AI_CONFIG_FILE": write(tmp_path, data), "TEAM_OPENROUTER_KEY": "sk-team"}
    )

    assert settings.scene_translation.credential_id == "team"
    assert settings.is_configured(settings.scene_translation)
    assert not settings.is_configured(settings.learning_task)
    assert settings.ai_config.credentials["team"].billing_group == "team-billing"

    seen = {}

    class FakeClient:
        def __init__(self, key, config, **options):
            seen.update(key=key, config=config, options=options)

        def generate(self, request):
            return TextModelResponse(
                output_text="{}", model_name="m", prompt_version=request.prompt_version
            )

    monkeypatch.setattr(registry, "OpenRouterTextClient", FakeClient)
    translator = registry.build_scene_translator(settings, build_tracer(settings))
    translator._client.generate(
        TextModelRequest(
            system_prompt="s",
            user_content="u",
            json_schema_name="n",
            json_schema={},
            prompt_version="v",
        )
    )
    assert seen["key"] == "sk-team"
    assert seen["config"].temperature == 0.3
    assert seen["options"] == {"allow_fallbacks": True, "fallback_models": ()}


def test_first_non_empty_variable_supplies_the_secret():
    config = parse_ai_config(example())
    secrets = resolve_credential_secrets(
        config, {"AI_OPENROUTER_API_KEY": "  ", "OPENROUTER_API_KEY": "sk-legacy"}
    )
    assert secrets == {"openrouter": "sk-legacy"}


def test_real_mode_names_missing_variables_without_values():
    with pytest.raises(AiConfigurationError) as raised:
        load_ai_settings(
            {
                "AI_MODE": "real",
                "AI_CONFIG_FILE": str(EXAMPLE),
                "AI_OPENAI_API_KEY": "sk-openai-secret",
            }
        )
    message = str(raised.value)
    assert "AI_OPENROUTER_API_KEY or OPENROUTER_API_KEY" in message
    assert "sceneAnalysis" in message
    assert "sk-openai-secret" not in message


def test_disabled_route_turns_the_feature_off(tmp_path):
    data = example()
    data["routes"]["ispyClue"] = {"enabled": False}
    settings = load_ai_settings(
        {"AI_MODE": "real", "AI_CONFIG_FILE": write(tmp_path, data), "AI_OPENROUTER_API_KEY": KEY}
    )

    assert settings.ispy_clue.provider is AiProvider.NONE
    assert registry.build_ispy_clue_generator(settings, build_tracer(settings)) is None


def _set(path: str, value):
    def mutate(data):
        *parents, leaf = path.split("/")
        target = data
        for part in parents:
            target = target[part]
        if value is _DELETE:
            del target[leaf]
        else:
            target[leaf] = value

    return mutate


_DELETE = object()
_ROUTE = "routes/sceneTranslation"
_DEPLOYMENT = f"deployments/{TRANSLATION}"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set(f"{_ROUTE}/deployments", ["missing"]), "unknown deployment 'missing'"),
        (_set(f"{_ROUTE}/deployments", [TRANSLATION, TRANSLATION]), "more than once"),
        (_set(f"{_ROUTE}/deployments", []), "needs at least one deployment"),
        (_set(f"{_ROUTE}/deadline_seconds", _DELETE), "needs deadline_seconds"),
        (_set(f"{_ROUTE}/deadline_seconds", 10), "deadline_seconds is shorter"),
        (_set(f"{_ROUTE}/max_model_calls", 1), "max_model_calls is below"),
        (_set(f"{_ROUTE}/policy", "roundRobin"), "routes.sceneTranslation.policy"),
        (_set("routes/ispyGuess", _DELETE), "routes.ispyGuess: missing route"),
        (_set("routes/chat", {"enabled": False}), "routes.chat"),
        (_set(f"{_DEPLOYMENT}/credentials", ["nope"]), "unknown credential 'nope'"),
        (_set(f"{_DEPLOYMENT}/credentials", ["openai"]), "is for adapter 'openai'"),
        (_set(f"{_DEPLOYMENT}/adapter", "none"), "unsupported adapter 'none'"),
        (_set(f"{_DEPLOYMENT}/capabilities", ["audio"]), f"deployments.{TRANSLATION}"),
        (_set(f"{_DEPLOYMENT}/model", ""), f"deployments.{TRANSLATION}.model"),
        (
            _set("deployments/scene-claude-haiku/capabilities", ["text", "jsonSchema"]),
            "lacks vision",
        ),
        (_set("credentials/openrouter/env", ["lower-case"]), "credentials.openrouter.env"),
        (_set("credentials/openrouter/env", []), "credentials.openrouter.env"),
    ],
)
def test_invalid_configuration_is_rejected(mutate, expected):
    data = example()
    mutate(data)
    with pytest.raises(AiConfigurationError) as raised:
        parse_ai_config(data)
    assert expected in str(raised.value)


def test_adapter_must_support_the_api():
    data = example()
    deployment = data["deployments"][TRANSLATION]
    deployment.update(adapter="gemini", credentials=["gemini"])
    with pytest.raises(AiConfigurationError, match="does not support api 'responses'"):
        parse_ai_config(data)


def test_errors_never_echo_values():
    data = example()
    data["credentials"]["openrouter"]["api_key"] = "sk-leak-123"
    data["deployments"][TRANSLATION]["defaults"]["timeout_seconds"] = "sk-leak-456"
    with pytest.raises(AiConfigurationError) as raised:
        parse_ai_config(data)
    message = str(raised.value)
    assert "credentials.openrouter.api_key" in message
    assert "sk-leak" not in message
    assert raised.value.__cause__ is None


def test_missing_and_malformed_files_are_reported(tmp_path):
    with pytest.raises(AiConfigurationError, match="not found"):
        load_ai_settings({"AI_CONFIG_FILE": str(tmp_path / "missing.toml")})
    broken = tmp_path / "broken.toml"
    broken.write_text("routes = [")
    with pytest.raises(AiConfigurationError, match="Invalid TOML"):
        load_ai_settings({"AI_CONFIG_FILE": str(broken)})


def test_loading_makes_no_network_calls(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access during configuration loading")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    load_ai_settings({"AI_CONFIG_FILE": str(EXAMPLE), "AI_OPENROUTER_API_KEY": KEY})
    load_ai_settings({"AI_OPENROUTER_API_KEY": KEY})


def test_secrets_are_kept_out_of_repr():
    settings = load_ai_settings(
        {
            "AI_CONFIG_FILE": str(EXAMPLE),
            "AI_OPENROUTER_API_KEY": KEY,
            "AI_OBSERVABILITY_SECRET_KEY": "lf-secret",
        }
    )
    assert KEY not in repr(settings)
    assert "lf-secret" not in repr(settings)
    assert KEY not in repr(settings.ai_config)
