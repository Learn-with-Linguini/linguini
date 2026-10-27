"""A0 missions with AI: translated nouns beyond the reviewed list, model-written lessons."""

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.ai.adapters.openai import OpenAITextClient
from app.ai.contracts.schema import build_pairs_json_schema, restore_maps
from app.ai.contracts.text import TextModelConfig
from app.ai.features.learning_tasks import LearningTaskService
from app.ai.features.learning_tasks.mission_a0 import A0_GENERATIONS, A0LessonResult
from app.ai.features.learning_tasks.mission_a0_situations import (
    A0_SITUATION_GENERATIONS,
    A0SituationLesson,
)
from app.ai.observability import NoOpAITracer
from app.missions import get_mission
from app.services import a0_lexicon as lex
from app.services.mission_registry import lesson_spec

# Objects outside REVIEWED_NOUNS, with what the scene translation returns for them.
TRANSLATED = {
    "es": [("sofa", "sofá", "el", "masculine", "sofás"),
           ("pillow", "almohada", "la", "feminine", "almohadas"),
           ("laptop", "portátil", "el", "masculine", "portátiles")],
    "fr": [("sofa", "canapé", "le", "masculine", "canapés"),
           ("computer", "ordinateur", "l'", "masculine", "ordinateurs"),
           ("pillow", "oreiller", "l'", "masculine", "oreillers")],
    "de": [("sofa", "Sofa", "das", "neuter", "Sofas"),
           ("pillow", "Kissen", "das", "neuter", "Kissen"),
           ("laptop", "Laptop", "der", "masculine", "Laptops")],
    "ko": [("sofa", "소파", None, None, "소파"),
           ("desk", "책상", None, None, "책상"),
           ("pillow", "베개", None, None, "베개")],
}
MISSIONS = ("M01", "M02", "M03", "M04", "M05", "M13")


def _word(language, translation, article):
    if language == "ko":
        return translation
    return f"{article}{translation}" if article == "l'" else f"{article} {translation}"


def _scene(language, rows=None):
    rows = rows or TRANSLATED[language]
    objects = [SimpleNamespace(id=uuid4(), label=label, attributes={}, bounding_box=None)
               for label, *_ in rows]
    words = [SimpleNamespace(display_text=_word(language, translation, article), id=uuid4())
             for _label, translation, article, _gender, _plural in rows]
    translated = {"objects": [
        dict(key=str(obj.id), source=label, translation=translation, article=article,
             gender=gender, plural=plural)
        for obj, (label, translation, article, gender, plural) in zip(objects, rows, strict=True)
    ]}
    return objects, words, translated


def _payload(mission_id, language, rows=None, *, quantity=2):
    objects, words, translated = _scene(language, rows)
    relations = []
    if mission_id == "M02":
        objects[0].attributes = {"color": "red"}
        relations = [SimpleNamespace(
            relation="on",
            subject_scene_object_id=objects[0].id,
            reference_scene_object_id=objects[1].id,
        )]
    mission = get_mission(mission_id, "A0", 2 if mission_id == "M02" else 1)
    spec = lesson_spec(mission)
    counts = [{"label": objects[0].label, "quantity": quantity,
               "sceneObjectIds": [str(objects[0].id)]}]
    context = {}
    if mission_id == "M04":
        context["learner_facts"] = {"ownedObjectId": str(objects[0].id), "pretend": False}
    elif mission_id == "M05":
        context["learner_facts"] = {"preference": {
            "sceneObjectIds": [str(objects[0].id)], "chosenObjectId": None,
            "reaction": "like",
        }}
    payload = spec.payload(
        mission, language, objects, relations, words, translated, counts, {}, uuid4(),
        context=context,
    )
    return spec, payload


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("mission_id", MISSIONS)
def test_objects_outside_the_reviewed_list_get_valid_lessons(mission_id, language):
    spec, payload = _payload(mission_id, language)
    assert payload["approvedObjects"], "translated nouns are approved"
    assert not any(row["reviewed"] for row in payload["approvedObjects"])
    assert spec.ready(payload)
    result = spec.generation.fallback(payload)
    spec.generation.validate(payload, result)


def test_translated_nouns_keep_their_grammar():
    _spec, payload = _payload("M13", "fr")
    rows = {row["source"]: row for row in payload["approvedObjects"]}
    assert rows["computer"]["chunk"] == "l'ordinateur" and rows["computer"]["elides"]
    assert rows["sofa"]["chunk"] == "le canapé"
    _spec, payload = _payload("M13", "ko")
    rows = {row["source"]: row for row in payload["approvedObjects"]}
    assert rows["desk"]["chunk"] == "책상이에요" and rows["sofa"]["chunk"] == "소파예요"
    _spec, payload = _payload("M01", "de")
    rows = {row["source"]: row for row in payload["approvedObjects"]}
    assert rows["sofa"]["identify"] == "Das ist ein Sofa."


@pytest.mark.parametrize("language, term", [
    ("es", dict(translation="sofá", article="la", gender="masculine")),  # article disagrees
    ("es", dict(translation="sofá", article="el", gender=None)),  # no gender
    ("es", dict(translation="sofá", article="el", gender="neuter")),  # no Spanish neuter
    ("fr", dict(translation="ordinateur", article=None, gender="masculine")),  # l' unknown
    ("es", dict(translation="es un sofá.", article="el", gender="masculine")),  # not a noun
    ("ko", dict(translation="sofa", article=None, gender=None)),  # not Hangul
    ("de", dict(translation="", article="das", gender="neuter")),
])
def test_unusable_translations_never_become_nouns(language, term):
    assert lex.translated_noun(language, term) is None


def test_korean_final_consonant_is_read_from_the_spelling():
    assert lex.korean_batchim("책상") is True
    assert lex.korean_batchim("소파") is False
    assert lex.korean_batchim("TV") is None


def test_reviewed_nouns_win_and_translations_fill_in_when_taught():
    # "cup" is reviewed as taza; the session taught vaso, so the translation is used.
    rows = [("cup", "vaso", "el", "masculine", "vasos"),
            ("sofa", "sofá", "el", "masculine", "sofás")]
    _spec, payload = _payload("M01", "es", rows)
    by_source = {row["source"]: row for row in payload["approvedObjects"]}
    assert by_source["cup"]["noun"] == "vaso" and not by_source["cup"]["reviewed"]
    rows[0] = ("cup", "taza", "la", "masculine", "tazas")  # model got the gender wrong
    _spec, payload = _payload("M01", "es", rows)
    cup = next(row for row in payload["approvedObjects"] if row["source"] == "cup")
    assert cup["gender"] == "feminine" and cup["reviewed"]


def test_counting_needs_a_known_plural():
    rows = [("sofa", "sofá", "el", "masculine", None),
            ("pillow", "almohada", "la", "feminine", "almohadas")]
    spec, payload = _payload("M03", "es", rows)
    assert not spec.ready(payload)
    spec, payload = _payload("M03", "es", rows[::-1], quantity=3)
    assert spec.ready(payload)
    assert payload["quantityChunks"]["3"] == "tres almohadas"


def test_a0_lessons_now_call_the_model_with_a_strict_schema():
    for generation in (*A0_GENERATIONS.values(), *A0_SITUATION_GENERATIONS.values()):
        assert generation.uses_model and generation.system_prompt
        schema = json.dumps(build_pairs_json_schema(generation.result_model))
        assert '"additionalProperties": {' not in schema, "no open maps reach the provider"


def _pairs(value):
    if isinstance(value, dict):
        return [{"key": key, "value": item} for key, item in value.items()]
    return value


def _as_model_reply(result):
    """A lesson as the model sends it: every map as a list of {key, value} pairs."""
    data = result.model_dump(mode="json", by_alias=True)
    for question in data["questions"]:
        for field in ("markerKeys", "optionObjectKeys", "optionIcons", "outcome"):
            if field in question:
                question[field] = _pairs(question[field])
        if question.get("dialogue"):
            question["dialogue"] = [_pairs(turn) for turn in question["dialogue"]]
    return data


@pytest.mark.parametrize("model", [A0LessonResult, A0SituationLesson])
def test_restore_maps_undoes_the_pairs_encoding(model):
    mission_id = "M02" if model is A0LessonResult else "M04"
    spec, payload = _payload(mission_id, "es")
    lesson = spec.generation.fallback(payload)
    restored = model.model_validate(restore_maps(model, _as_model_reply(lesson)))
    assert restored == lesson


@pytest.mark.parametrize("mission_id", ["M01", "M05"])
def test_generate_mission_accepts_a_model_written_lesson(mission_id):
    spec, payload = _payload(mission_id, "fr")
    lesson = spec.generation.fallback(payload)
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "status": "completed", "model": "test-model", "error": None,
            "incomplete_details": None, "instructions": None,
            "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "output": [{
                "id": "msg_test", "type": "message", "role": "assistant",
                "status": "completed", "content": [{
                    "type": "output_text", "text": json.dumps(_as_model_reply(lesson)),
                    "annotations": [],
                }],
            }],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        })

    client = OpenAITextClient(
        "not-a-real-key", TextModelConfig(model_name="test-model"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    result = LearningTaskService(
        client, TextModelConfig(model_name="test-model"), tracer=NoOpAITracer(),
        provider="openai",
    ).generate_mission(payload, spec.generation, mission_version="1")

    assert result == lesson
    assert len(calls) == 1
    sent = calls[0]["text"]["format"]
    assert sent["strict"] is True
    assert '"additionalProperties": {' not in json.dumps(sent["schema"])
