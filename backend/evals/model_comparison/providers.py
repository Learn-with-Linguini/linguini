"""Candidate models per AI call, and the production services that run them.

Every candidate is built through the same seams the app uses: a
``TextModelClient`` or ``VisionModelClient`` from ``app.ai.registry``, wrapped
in a recorder and handed to the real feature service. Prompts, schemas and
validators are therefore the ones the app ships.

OpenRouter models are named ``vendor/model``; OpenAI and Gemini models are
called directly, so their latency excludes OpenRouter's routing hop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from typing import Any

from app.ai.observability import NoOpAITracer
from app.ai.registry import build_text_client, build_vision_client
from app.ai.settings import AiProvider, AiSettings, load_ai_settings
from app.ai.text_model import TextModelConfig
from app.services.vision_model import VisionModelConfig

from . import pricing
from .recording import Overrides, RecordingClient

CALLS = ("scene_analysis", "translation", "learning_tasks", "ispy_clues", "ispy_guess")
TRACER = NoOpAITracer()


@dataclass(frozen=True)
class Candidate:
    provider: str  # openai | gemini | openrouter
    model: str

    @property
    def catalogue_id(self) -> str:
        return pricing.catalogue_id(self.provider, self.model)

    @property
    def ai_provider(self) -> AiProvider:
        return AiProvider(self.provider)

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def _c(spec: str) -> Candidate:
    provider, model = spec.split(":", 1)
    return Candidate(provider, model)


# Third-party models reachable only through OpenRouter, plus the two Gemini
# models used for the calls whose adapter is OpenAI-shaped.
_THIRD_PARTY = [
    "openrouter:anthropic/claude-haiku-4.5",
    "openrouter:qwen/qwen3.8-flash",
    "openrouter:deepseek/deepseek-v4-flash",
]
_TEXT_CHEAP = [
    "openai:gpt-4o-mini", "openai:gpt-4.1-mini", "openai:gpt-4.1-nano",
    "gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite",
    *_THIRD_PARTY,
]

# Current production defaults are in every list, so the comparison answers
# whether today's choice was right.
CANDIDATES: dict[str, list[Candidate]] = {
    "scene_analysis": [_c(s) for s in (
        "openai:gpt-4o", "openai:gpt-4.1-mini", "openai:gpt-5.4-nano",
        "gemini:gemini-3.7-flash", "gemini:gemini-3.5-flash-lite",
        "gemini:gemini-3.1-flash-lite",
        *_THIRD_PARTY[:1], "openrouter:qwen/qwen3.8-flash",
        "openrouter:meta-llama/llama-4-maverick",
    )],
    "translation": [_c(s) for s in (
        *_TEXT_CHEAP, "gemini:gemini-3.7-flash",
        "openrouter:mistralai/mistral-small-2603",
    )],
    "learning_tasks": [_c(s) for s in (
        "openai:gpt-4o-mini", "openai:gpt-4.1-mini", "openai:gpt-5.4-mini",
        "gemini:gemini-3.5-flash-lite", "gemini:gemini-3.7-flash", *_THIRD_PARTY,
    )],
    "ispy_clues": [_c(s) for s in _TEXT_CHEAP],
    # The guess adapter is OpenAI-SDK-shaped, so Gemini models are reached
    # through OpenRouter rather than the Gemini SDK.
    "ispy_guess": [_c(s) for s in (
        "openai:gpt-4o-mini", "openai:gpt-4.1-mini", "openai:gpt-4.1-nano",
        *_THIRD_PARTY, "openrouter:google/gemini-3.5-flash-lite",
    )],
}

PRODUCTION_DEFAULTS = {
    "scene_analysis": "gemini:gemini-3.7-flash",
    "translation": "gemini:gemini-3.5-flash-lite",
    "learning_tasks": "openai:gpt-4o-mini",
    "ispy_clues": "openai:gpt-4o-mini",
    "ispy_guess": "openai:gpt-4o-mini",
}

# Judge for the open-ended calls. Not a candidate anywhere, though it shares a
# family with the claude-haiku-4.5 candidate; the report flags that.
JUDGE = Candidate("openrouter", "anthropic/claude-sonnet-5")

TIMEOUTS = {"scene_analysis": 180, "learning_tasks": 120}
MAX_OUTPUT_TOKENS = {"learning_tasks": 8000, "scene_analysis": 3000}


def all_catalogue_ids() -> set[str]:
    ids = {c.catalogue_id for cands in CANDIDATES.values() for c in cands}
    return ids | {JUDGE.catalogue_id}


@cache
def facts() -> dict[str, pricing.ModelFacts]:
    return pricing.load()


@cache
def settings() -> AiSettings:
    loaded = load_ai_settings()
    for provider, name in (
        (AiProvider.OPENAI, "OPENAI_API_KEY"),
        (AiProvider.GEMINI, "GEMINI_API_KEY"),
        (AiProvider.OPENROUTER, "OPENROUTER_API_KEY"),
    ):
        if not loaded.api_key_for(provider) and not os.getenv(name, "").strip():
            raise SystemExit(f"{name} is not set; load backend/.env.local first")
    return loaded


def text_config(call: str, cand: Candidate, overrides: Overrides) -> TextModelConfig:
    return overrides.applied_to(TextModelConfig(
        model_name=cand.model,
        timeout_seconds=TIMEOUTS.get(call, 60),
        max_output_tokens=MAX_OUTPUT_TOKENS.get(call, 1500),
        max_retries=0,
    ))


def vision_config(call: str, cand: Candidate, overrides: Overrides) -> VisionModelConfig:
    return overrides.applied_to(VisionModelConfig(
        model_name=cand.model,
        timeout_seconds=TIMEOUTS.get(call, 120),
        max_output_tokens=MAX_OUTPUT_TOKENS.get(call, 1500),
        max_retries=0,
    ))


def recording_text_client(cand: Candidate, config: TextModelConfig) -> RecordingClient:
    inner = build_text_client(cand.ai_provider, settings(), config)
    return RecordingClient(
        inner, facts()[cand.catalogue_id], gemini=cand.provider == "gemini"
    )


def recording_vision_client(
    cand: Candidate, config: VisionModelConfig
) -> RecordingClient:
    inner = build_vision_client(cand.ai_provider, settings(), config)
    return RecordingClient(
        inner, facts()[cand.catalogue_id], gemini=cand.provider == "gemini"
    )


def openai_sdk_client(cand: Candidate, timeout_seconds: int) -> Any:
    """Raw SDK client for the I-Spy guess adapter, which is not on the text seam."""
    from openai import OpenAI

    from app.ai.openrouter import OPENROUTER_BASE_URL

    base_url = OPENROUTER_BASE_URL if cand.provider == "openrouter" else None
    return OpenAI(
        api_key=settings().api_key_for(cand.ai_provider),
        timeout=timeout_seconds,
        max_retries=0,
        **({"base_url": base_url} if base_url else {}),
    )
