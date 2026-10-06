"""TOML AI configuration: the default file, custom files and validation."""

import copy
import json
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

DEFAULT = Path(__file__).resolve().parents[1] / "ai.toml"
KEY = "sk-or-test-secret"
TRANSLATION = "translation-gpt-4o-mini"


def example() -> dict:
    return copy.deepcopy(tomllib.loads(DEFAULT.read_text()))


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


def test_default_file_loads_when_ai_config_file_is_unset():
    env = {"AI_OPENROUTER_API_KEY": KEY}
    settings = load_ai_settings(env)

    assert settings == load_ai_settings({**env, "AI_CONFIG_FILE": str(DEFAULT)})
    for feature in AiFeature:
        config = settings.feature(feature)
        assert config.provider is AiProvider.OPENROUTER
        assert settings.is_configured(config)
        assert settings.secret_for(config) == KEY
    route = settings.ai_config.routes[AiFeature.SCENE_TRANSLATION]
    assert route.policy is SelectionPolicy.PRIORITY
    assert (route.deadline_seconds, route.max_model_calls) == (120, 2)
    assert settings.scene_translation.deployment_id == TRANSLATION
    deployment = settings.ai_config.deployments["scene-claude-haiku"]
    assert deployment.api is ApiType.RESPONSES
    assert Capability.VISION in deployment.capabilities
    assert settings.ai_config.credentials["openrouter"].env == ("AI_OPENROUTER_API_KEY",)


def test_custom_file_replaces_the_default(tmp_path):
    data = example()
    data["deployments"][TRANSLATION]["model"] = "custom/model"
    settings = load_ai_settings({"AI_CONFIG_FILE": write(tmp_path, data)})

    assert settings.scene_translation.model_name == "custom/model"
    assert load_ai_settings({}).scene_translation.model_name == "openai/gpt-4o-mini"


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
    data = example()
    data["credentials"]["openrouter"]["env"] = ["AI_OPENROUTER_API_KEY", "TEAM_KEY"]
    config = parse_ai_config(data)
    secrets = resolve_credential_secrets(
        config, {"AI_OPENROUTER_API_KEY": "  ", "TEAM_KEY": "sk-team"}
    )
    assert secrets == {"openrouter": "sk-team"}


def test_real_mode_names_missing_variables_without_values():
    with pytest.raises(AiConfigurationError) as raised:
        load_ai_settings(
            {
                "AI_MODE": "real",
                "AI_CONFIG_FILE": str(DEFAULT),
                "AI_OPENAI_API_KEY": "sk-openai-secret",
            }
        )
    message = str(raised.value)
    assert "(set AI_OPENROUTER_API_KEY)" in message
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

    load_ai_settings({"AI_CONFIG_FILE": str(DEFAULT), "AI_OPENROUTER_API_KEY": KEY})
    load_ai_settings({"AI_OPENROUTER_API_KEY": KEY})


def test_secrets_are_kept_out_of_repr():
    settings = load_ai_settings(
        {
            "AI_CONFIG_FILE": str(DEFAULT),
            "AI_OPENROUTER_API_KEY": KEY,
            "AI_OBSERVABILITY_SECRET_KEY": "lf-secret",
        }
    )
    assert KEY not in repr(settings)
    assert "lf-secret" not in repr(settings)
    assert KEY not in repr(settings.ai_config)
