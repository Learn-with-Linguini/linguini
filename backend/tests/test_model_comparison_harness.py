"""The model comparison harness sweeps reasoning effort and checks only the keys it uses."""

from types import SimpleNamespace

import pytest

from app.ai.contracts.text import TextModelConfig
from evals.model_comparison import providers
from evals.model_comparison.recording import Overrides
from evals.model_comparison.run import parse_grid


def test_reasoning_effort_sweeps_onto_the_model_config():
    grid = parse_grid(["reasoning_effort=low,medium"])

    assert grid == [Overrides(reasoning_effort="low"), Overrides(reasoning_effort="medium")]
    config = grid[0].applied_to(TextModelConfig(model_name="m"))
    assert config.reasoning_effort == "low"
    assert grid[0].label() == "reasoning_effort=low"


def test_unknown_reasoning_effort_is_refused():
    with pytest.raises(SystemExit):
        parse_grid(["reasoning_effort=extreme"])


def test_only_the_providers_a_run_calls_need_keys(monkeypatch):
    keys = {"openai": "sk-openai", "gemini": "sk-gemini"}
    fake = SimpleNamespace(api_key_for=lambda provider: keys.get(provider.value))
    monkeypatch.setattr(providers, "settings", lambda: fake)

    providers.require_keys({"openai", "gemini"})
    with pytest.raises(SystemExit, match="AI_OPENROUTER_API_KEY"):
        providers.require_keys({"openai", "openrouter"})
