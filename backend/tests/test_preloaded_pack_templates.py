"""Curated-scene templates for a language with a ready pack: lessons and I-Spy games apart."""

from uuid import uuid4

from test_preloaded_templates import RESERVE, SceneModel, scene_row, services, unlimited

from app.ai.cache import GENERATED_CONTENT_KEY, TemplateSet
from app.language_packs.context import resolve_language_context
from app.repositories.postgres.workflow import ispy_clue_payload, learning_task_payload
from app.scripts.preloaded_templates import curated_generation_inputs, generate_row_templates

STAGES = ["translation", "clues", "pack-translation", "pack-lessons", "pack-clues"]


def _precomputed(model=None):
    row = scene_row()
    model = model or SceneModel()
    outcomes = generate_row_templates(row, "es", services(model), unlimited(), RESERVE)
    assert [(outcome.stage, outcome.status) for outcome in outcomes] == [
        (stage, "generated") for stage in STAGES
    ]
    return row, model


def _session(row, model, language_context, *, lesson=True):
    """The calls a learner session makes: a lesson, or (``lesson=False``) an I-Spy game."""
    payload, objects, relations = curated_generation_inputs(row, "es", uuid4())
    templates = TemplateSet.from_content([row["content"]])
    feature = services(model)
    options = {"language_context": language_context} if language_context else {}
    translated = feature["translation"].translate(payload, templates=templates, **options)
    lessons = feature["lessons"].generate(
        learning_task_payload(payload, translated, relations), templates=templates
    ) if lesson else None
    clues = feature["clues"].generate(
        ispy_clue_payload(payload, translated, objects, relations), templates=templates
    )
    return translated, lessons, clues


def test_a_pack_language_stores_lesson_and_game_templates_side_by_side():
    row, model = _precomputed()
    stored = row["content"][GENERATED_CONTENT_KEY]["templates"]
    by_feature = {}
    for entry in stored:
        by_feature.setdefault(entry["feature"], set()).add(
            (entry["variant"].split("|")[0], entry.get("basis", ""))
        )
    assert by_feature["sceneTranslation"] == {
        ("scene-translation.v5", ""), ("pack-translation.v2", ""),
    }
    # Lessons only ever use the pack translation; clues serve lessons and I-Spy games.
    assert {basis for _variant, basis in by_feature["learningTask"]} == {"pack"}
    assert {basis for _variant, basis in by_feature["ispyClue"]} == {"", "pack"}
    # The pack translation was reviewed once, when its template was made.
    assert model.requests.count("pack_translation_review") == 1


def test_an_unchanged_scene_builds_a_pack_lesson_without_any_call():
    row, _ = _precomputed()
    model = SceneModel(error=AssertionError("provider must not be called"))
    translated, lessons, clues = _session(row, model, resolve_language_context("es"))
    assert model.requests == []
    assert all(term.native_display for term in translated.objects)
    assert lessons.tasks and clues.clues


def test_i_spy_games_keep_the_unguided_templates():
    row, _ = _precomputed()
    model = SceneModel(error=AssertionError("provider must not be called"))
    translated, _lessons, clues = _session(row, model, None, lesson=False)
    assert model.requests == []
    assert not any(term.native_display for term in translated.objects)
    assert clues.clues


def test_a_rerun_reuses_both_template_sets_without_calls():
    row, _ = _precomputed()
    model = SceneModel()
    outcomes = generate_row_templates(row, "es", services(model), unlimited(), RESERVE)
    assert [outcome.status for outcome in outcomes] == ["reused"] * len(STAGES)
    assert model.requests == []
