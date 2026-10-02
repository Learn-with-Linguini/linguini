import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.services.ispy_guess import ISpyGuessError, scene_guess_response_model
from app.services.openai_ispy_guess import OpenAIISpyGuessGenerator

CONTEXT = {
    "targetLanguage": "es",
    "sceneObjects": {
        "objects": [
            {"key": "object_1", "source": "cup", "translation": "taza"},
            {"key": "object_2", "source": "table", "translation": "mesa"},
        ],
        "attributes": [{
            "key": "object_1:color", "objectKey": "object_1",
            "source": "red", "translation": "roja",
        }],
        "relations": [],
    },
}


def result():
    return {
        "guessedObjectKey": "object_1",
        "ambiguous": False,
        "alternativeObjectKeys": [],
        "matchedEvidenceKeys": ["object_1:color"],
        "contradictedEvidenceKeys": [],
        "feedback": "Great clue! The colour makes the object clear.",
    }


def generator(tmp_path: Path, data):
    prompt = tmp_path / "i_spy_guess.txt"
    prompt.write_text("Guess the object.", encoding="utf-8")

    def parse(**kwargs):
        return SimpleNamespace(output_parsed=kwargs["text_format"].model_validate(data))

    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(side_effect=parse)))
    return (
        OpenAIISpyGuessGenerator("test-key", "test-model", client=client, prompt_path=prompt),
        client,
    )


def test_guess_receives_scene_facts_and_learner_text_but_no_selected_target(tmp_path):
    provider, client = generator(tmp_path, result())

    guess = provider.guess(CONTEXT, "Es roja.")

    assert guess.guessed_object_key == "object_1"
    payload = json.loads(client.responses.parse.call_args.kwargs["input"])
    assert payload["learnerText"] == "Es roja."
    assert "selectedTargetObjectKey" not in payload


def test_schema_rejects_a_guess_outside_the_scene():
    data = result()
    data["guessedObjectKey"] = "other-object"
    payload = {**CONTEXT, "learnerText": "Es roja."}
    with pytest.raises(ValidationError):
        scene_guess_response_model(payload).model_validate(data)


def test_rejects_an_alternative_that_repeats_the_guess(tmp_path):
    data = result()
    data["ambiguous"] = True
    data["alternativeObjectKeys"] = ["object_1"]
    provider, _ = generator(tmp_path, data)
    with pytest.raises(ISpyGuessError):
        provider.guess(CONTEXT, "Es roja.")


def test_a_base_url_points_the_same_adapter_at_openrouter(tmp_path: Path):
    """OpenRouter speaks the same Responses API, so only the host changes."""
    prompt = tmp_path / "i_spy_guess.txt"
    prompt.write_text("Guess the object.", encoding="utf-8")

    provider = OpenAIISpyGuessGenerator(
        "test-key", "anthropic/claude-haiku-4.5",
        prompt_path=prompt, base_url="https://openrouter.ai/api/v1",
    )

    assert str(provider.client.base_url).startswith("https://openrouter.ai/api/v1")


def test_without_a_base_url_the_adapter_calls_openai(tmp_path: Path):
    prompt = tmp_path / "i_spy_guess.txt"
    prompt.write_text("Guess the object.", encoding="utf-8")

    provider = OpenAIISpyGuessGenerator("test-key", "gpt-4o-mini", prompt_path=prompt)

    assert "openai.com" in str(provider.client.base_url)
