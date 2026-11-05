"""Free-form maps travel as [{key, value}] lists in strict structured output."""

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.contracts.schema import build_pairs_json_schema, restore_maps


class Option(BaseModel):
    label: str
    scores: dict[str, int]


class Lesson(BaseModel):
    title: str
    markers: dict[str, str]
    options: list[Option]


def test_maps_are_sent_as_pairs_and_restored():
    schema = build_pairs_json_schema(Lesson)
    # Strict output rejects open maps, so no free-form object is left in the schema.
    assert '"additionalProperties": {' not in json.dumps(schema)
    reply = {
        "title": "Find it",
        "markers": [{"key": "marker-1", "value": "cup"}, {"key": "marker-2", "value": "book"}],
        "options": [{"label": "taza", "scores": [{"key": "a", "value": 1}]}],
    }
    restored = Lesson.model_validate(restore_maps(Lesson, reply))
    assert restored.markers == {"marker-1": "cup", "marker-2": "book"}
    assert restored.options[0].scores == {"a": 1}


class Card(BaseModel):
    forms: dict[Literal["masculine", "feminine"], str] = Field(description="Forms by gender.")


def test_literal_map_keys_and_description_survive_as_pairs():
    forms = build_pairs_json_schema(Card)["properties"]["forms"]
    assert forms["items"]["properties"]["key"] == {
        "type": "string", "enum": ["masculine", "feminine"],
    }
    assert forms["description"] == "Forms by gender."
