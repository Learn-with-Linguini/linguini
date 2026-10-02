"""Model prices and capability facts, from OpenRouter's public model catalogue.

OpenRouter passes provider list prices through unchanged, so its catalogue is
also the price list for calls made directly to OpenAI and Gemini. A trimmed
snapshot is committed so results can be re-costed and the report rebuilt
without network access; ``refresh`` updates it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).parent / "pricing_snapshot.json"
MODELS_URL = "https://openrouter.ai/api/v1/models"

# Direct-provider model ids -> OpenRouter catalogue ids.
_PREFIX = {"openai": "openai/", "gemini": "google/", "openrouter": ""}


@dataclass(frozen=True)
class ModelFacts:
    catalogue_id: str
    input_per_mtok: float
    output_per_mtok: float
    context_length: int | None
    max_output_tokens: int | None
    vision: bool
    structured_outputs: bool
    temperature: bool
    reasoning: bool

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        """Output includes reasoning/thinking tokens, which are billed as output."""
        return (
            input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok
        ) / 1_000_000


def catalogue_id(provider: str, model: str) -> str:
    return _PREFIX[provider] + model


def _facts(entry: dict[str, Any]) -> ModelFacts:
    pricing = entry.get("pricing", {})
    params = set(entry.get("supported_parameters", []))
    top = entry.get("top_provider") or {}
    return ModelFacts(
        catalogue_id=entry["id"],
        input_per_mtok=float(pricing.get("prompt", 0)) * 1_000_000,
        output_per_mtok=float(pricing.get("completion", 0)) * 1_000_000,
        context_length=entry.get("context_length"),
        max_output_tokens=top.get("max_completion_tokens"),
        vision="image" in entry.get("architecture", {}).get("input_modalities", []),
        structured_outputs="structured_outputs" in params,
        temperature="temperature" in params,
        reasoning="reasoning" in params,
    )


def load() -> dict[str, ModelFacts]:
    entries = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: _facts(entry) for entry in entries}


def refresh(model_ids: set[str]) -> None:
    import httpx

    entries = httpx.get(MODELS_URL, timeout=60).json()["data"]
    keep = [
        {
            key: entry.get(key)
            for key in (
                "id", "name", "created", "context_length", "pricing",
                "supported_parameters", "architecture", "top_provider",
            )
        }
        for entry in entries
        if entry["id"] in model_ids
    ]
    missing = model_ids - {entry["id"] for entry in keep}
    if missing:
        raise SystemExit(f"not in OpenRouter catalogue: {sorted(missing)}")
    SNAPSHOT_PATH.write_text(
        json.dumps(sorted(keep, key=lambda e: e["id"]), indent=1) + "\n", encoding="utf-8"
    )
