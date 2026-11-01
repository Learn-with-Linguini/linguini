"""Free-form maps travel as [{key, value}] lists in strict structured output."""

import json

from pydantic import BaseModel

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
