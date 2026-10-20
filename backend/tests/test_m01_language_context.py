"""Shared-context contracts using Spanish variants and mocked providers only."""

import json
import shutil
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_language_pack_runtime import MockSpanishProvider, service
from test_language_pack_runtime import runtime as runtime

from app.ai.cache.cache import ResultCache
from app.ai.cache.store import CacheScope
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.translation.service import SceneTranslationService
from app.ai.features.translation.validation import SceneTranslationError
from app.ai.observability import NoOpAITracer
from app.language_packs.context import operation_context, resolve_language_context
from app.language_packs.runtime import session_inputs
from app.missions import get_mission
from app.repositories.postgres.workflow import PostgresWorkflowRepository, translation_payload
from app.schemas.enums import PartOfSpeech
from app.schemas.tasks import SessionTask
from app.services.mission_eligibility import lesson_missions, photo_eligibility
from app.services.session_plan import build_tasks

SPANISH = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


@pytest.fixture
def pack_dir(runtime, tmp_path, monkeypatch):
    destination = tmp_path / "es-ES" / "everyday"
    shutil.copytree(SPANISH, destination)
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(destination))
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REGISTER", "everyday")
    return destination


class MockTranslationProvider:
    def __init__(self, missing=None):
        self.requests = []
        self.missing = missing

    def generate(self, request):
        self.requests.append(request)
        data = json.loads(request.user_content)
        context = data.get("language_context", {}).get("context", {})
        words = {
            "cup": "taza",
            "book": "libro",
            "table": "mesa",
            "red": "rojo",
            "green": "verde",
            "white": "blanco",
            "on": "sobre",
        }
        result = {}
        for field in ("objects", "attributes", "relationships"):
            result[field] = []
            for row in data[field]:
                noun = words.get(row["source"], row["source"])
                article = "el" if noun == "libro" else "la"
                article = article if field == "objects" else None
                gender = ("masculine" if article == "el" else "feminine") if article else None
                if context.get("articles") == "none":
                    article = None
                if context.get("grammaticalGender") == "none":
                    gender = None
                display = " ".join(filter(None, [article, noun]))
                term = dict(
                    **row,
                    translation=noun,
                    article=article,
                    gender=gender,
                    nativeDisplay=display,
                    romanization=display,
                    phoneticText="LEGACY sounds",
                )
                if self.missing:
                    term[self.missing] = None
                result[field].append(term)
        return TextModelResponse(
            output_text=json.dumps(result, ensure_ascii=False),
            model_name="mocked-Spanish",
            prompt_version=request.prompt_version,
        )


def translator(provider, cache=None):
    return SceneTranslationService(
        provider,
        TextModelConfig(model_name="mocked-Spanish", max_retries=0),
        tracer=NoOpAITracer(),
        provider="mock",
        cache=cache,
    )


def payload(runtime):
    return translation_payload("es", "Spanish fixture", "Confirmed facts", runtime[0], runtime[1])


def cards(context, runtime, translated):
    words = [
        SimpleNamespace(
            id=UUID(int=10 + i),
            display_text=term.translation,
            part_of_speech=PartOfSpeech.NOUN,
            gender=term.gender,
            phonetic_text=term.phonetic_text,
            example_sentence=None,
            language_code="es",
        )
        for i, term in enumerate(translated.objects)
    ]
    translations = [SimpleNamespace(translated_text=term.source) for term in translated.objects]
    tasks = build_tasks(
        UUID(int=100), runtime[0], words, translations, False, translated, language_context=context
    )
    return tasks[0], words


def test_context_reaches_translation_cards_and_m01_without_reresolution(
    pack_dir, runtime, monkeypatch
):
    context = resolve_language_context("es")
    provider = MockTranslationProvider()
    translated = translator(provider).translate(payload(runtime), language_context=context)
    intro, words = cards(context, runtime, translated)
    # Configuration changes after capture must not change the chosen language path.
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "false")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "missing/*")
    generator = MockSpanishProvider()
    task = service(generator).generate_pack_m01(
        get_mission("M01", "A1", 1),
        "es",
        runtime[0],
        runtime[1],
        words,
        translated,
        session_id=UUID(int=100),
        review_markers={},
        language_context=context,
    )
    original = json.loads(provider.requests[0].user_content)["language_context"]["context"]
    assert intro.public_content.language_context == task.public_content.language_context
    assert original["fingerprint"] == context.display.fingerprint
    assert all(
        json.loads(request.user_content)["language_context"]["fingerprint"]
        == original["fingerprint"]
        for request in generator.requests
    )
    assert task.public_content.language_context.register_id == "everyday"
    with pytest.raises(FrozenInstanceError):
        context.pack_json = "changed"
    copy = context.pack
    copy.pack_version += 1
    assert context.pack.pack_version != copy.pack_version


def test_guidance_and_register_change_translation_cache_identity(pack_dir, runtime, monkeypatch):
    provider, cache = MockTranslationProvider(), ResultCache()
    feature = translator(provider, cache)
    scope = CacheScope.user("Spanish-context-test")
    context = resolve_language_context("es")
    for _ in range(2):
        feature.translate(payload(runtime), language_context=context, cache_scope=scope)
    assert len(provider.requests) == 1
    path = pack_dir / "constructions" / "identify-object.toml"
    path.write_text(
        path.read_text("utf-8").replace('summary = "', 'summary = "Revised: ', 1), "utf-8"
    )
    changed = resolve_language_context("es")
    assert changed.display.fingerprint != context.display.fingerprint
    feature.translate(payload(runtime), language_context=changed, cache_scope=scope)
    assert len(provider.requests) == 2
    # The old operation remains pinned even after files changed.
    feature.translate(payload(runtime), language_context=context, cache_scope=scope)
    assert len(provider.requests) == 2
    alternate = pack_dir.parent / "formal"
    shutil.copytree(pack_dir, alternate)
    manifest = alternate / "pack.toml"
    manifest.write_text(
        manifest.read_text("utf-8")
        .replace('register_id = "everyday"', 'register_id = "formal"')
        .replace('pack_id = "es-es-everyday"', 'pack_id = "es-test-formal"'),
        "utf-8",
    )
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(pack_dir.parent))
    formal = resolve_language_context("es", "formal")
    feature.translate(payload(runtime), language_context=formal, cache_scope=scope)
    assert len(provider.requests) == 3
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REGISTER", "")
    with pytest.raises(ValueError, match="specify a register"):
        resolve_language_context("es")
    with pytest.raises(ValueError, match="no pack"):
        resolve_language_context("es", "missing")


def configure_requirements(pack_dir):
    manifest = pack_dir / "pack.toml"
    manifest.write_text(
        manifest.read_text("utf-8")
        .replace('articles = "required"', 'articles = "none"')
        .replace('grammatical_gender = "required"', 'grammatical_gender = "none"')
        .replace(
            'code = "es"',
            'code = "es"\nromanization_required = true\n'
            'romanization_convention = "Spanish Latin spelling"',
        ),
        "utf-8",
    )
    labels = pack_dir / "labels.toml"
    # This Spanish-only variant uses identity Latin spelling for fixed labels.
    lines = labels.read_text("utf-8").splitlines()
    lines = [
        entry
        for line in lines
        for entry in (
            [line, "romanization = " + line.removeprefix("text = ")]
            if line.startswith("text = ")
            else [line]
        )
    ]
    labels.write_text("\n".join(lines) + "\n", "utf-8")


def test_native_display_transliteration_and_metadata_survive_saved_task(pack_dir, runtime):
    configure_requirements(pack_dir)
    context = resolve_language_context("es")
    result = translator(MockTranslationProvider()).translate(
        payload(runtime), language_context=context
    )
    intro, _ = cards(context, runtime, result)
    card = intro.public_content.words[0]
    assert card.target_text == "taza"  # No automatic article prefix.
    assert card.gender is None
    assert card.romanization == "taza"
    assert card.phonetic_text == "LEGACY sounds"
    restored = SessionTask.model_validate_json(intro.model_dump_json())
    assert restored.public_content.language_context == context.display
    assert restored.public_content.words[0].romanization == "taza"
    assert restored.public_content.questions[0].romanizations["taza"] == "taza"


@pytest.mark.parametrize("missing", ["nativeDisplay", "romanization"])
def test_required_preparation_fields_fail_before_cards_are_published(pack_dir, runtime, missing):
    configure_requirements(pack_dir)
    context = resolve_language_context("es")
    with pytest.raises(SceneTranslationError, match="unusable output"):
        translator(MockTranslationProvider(missing)).translate(
            payload(runtime), language_context=context
        )


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_scene_suitability_not_legacy_dictionary_membership(pack_dir, runtime, level):
    context = resolve_language_context("es")
    for index, obj in enumerate(runtime[0]):
        obj.label = f"unlisted keepsake {index}"
        obj.attributes = {"color": "unlisted crimson shade"}
    mission = get_mission("M01", level, 1)
    assert photo_eligibility(mission, runtime[0], runtime[1], language_context=context).eligible
    assert mission in lesson_missions(
        "lesson", {"target_language_code": "es", "proficiency_level": level}, context
    )
    if level == "A0":
        assert not photo_eligibility(mission, runtime[0], runtime[1]).eligible


def test_flag_off_and_old_saved_tasks_need_no_context(pack_dir, runtime, monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "false")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "missing/*")
    assert resolve_language_context("es") is None
    # Legacy service retains its prompt and schema; optional additions stay absent.
    provider = MockTranslationProvider()
    translator(provider).translate(payload(runtime))
    request = provider.requests[0]
    assert "language_context" not in json.loads(request.user_content)
    assert (
        "nativeDisplay" not in request.json_schema["properties"]["objects"]["items"]["properties"]
    )


def test_session_forms_ignore_stale_catalog_gender(pack_dir, runtime):
    context = resolve_language_context("es")
    translated = translator(MockTranslationProvider()).translate(
        payload(runtime),
        language_context=context,
    )
    intro, words = cards(context, runtime, translated)
    for word in words:
        word.gender = "neuter"  # A reused historical catalog row.
    _, vocabulary = session_inputs(context.pack, runtime[0], runtime[1], words, translated, {})
    assert vocabulary.terms[0].agreement == translated.objects[0].gender
    assert intro.public_content.words[0].gender == translated.objects[0].gender


@pytest.mark.parametrize("field", ["article", "gender"])
def test_pack_declared_required_fields_are_enforced(pack_dir, runtime, field):
    context = resolve_language_context("es")
    with pytest.raises(SceneTranslationError, match="unusable output"):
        translator(MockTranslationProvider(field)).translate(
            payload(runtime), language_context=context
        )


def test_translation_rejects_a_different_context_language(pack_dir, runtime):
    context = resolve_language_context("es")
    provider = MockTranslationProvider()
    request = {**payload(runtime), "targetLanguage": "es-MX"}
    with pytest.raises(SceneTranslationError, match="does not match"):
        translator(provider).translate(request, language_context=context)
    assert not provider.requests


def test_saved_legacy_vocabulary_task_can_reload_without_new_metadata(
    pack_dir, runtime, monkeypatch
):
    translated = translator(MockTranslationProvider()).translate(payload(runtime))
    intro, _ = cards(None, runtime, translated)
    serialized = intro.model_dump_json()
    assert "languageContext" not in serialized
    assert "romanization" not in serialized
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "true")
    restored = SessionTask.model_validate_json(serialized)
    assert restored.public_content.language_context is None
    assert restored.public_content.words[0].target_text == intro.public_content.words[0].target_text


def test_missing_target_preparation_label_has_no_english_fallback(pack_dir, runtime):
    context = resolve_language_context("es")
    pack = context.pack
    pack.labels = [label for label in pack.labels if label.semantic != "vocabulary-unsure"]
    context = replace(context, pack_json=pack.model_dump_json(by_alias=False))
    translated = translator(MockTranslationProvider()).translate(
        payload(runtime), language_context=context
    )
    translated = translated.model_copy(
        update={
            "objects": translated.objects[:1],
            "attributes": [],
            "relationships": [],
        }
    )
    with pytest.raises(ValueError, match="vocabulary-unsure"):
        cards(context, (runtime[0][:1], runtime[1]), translated)


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_pack_context_preserves_other_mission_availability(pack_dir, runtime, level):
    context = resolve_language_context("es")
    profile = {"target_language_code": "es", "proficiency_level": level}
    legacy = lesson_missions("lesson", profile, None)
    enabled = lesson_missions("lesson", profile, context)
    assert [m for m in enabled if m.mission_id != "M01"] == [
        m for m in legacy if m.mission_id != "M01"
    ]
    for mission in legacy:
        if mission.mission_id != "M01":
            assert photo_eligibility(mission, runtime[0], runtime[1], language_context=context) == (
                photo_eligibility(mission, runtime[0], runtime[1])
            )


def test_analysis_snapshot_is_reused_without_discovery(pack_dir, runtime, monkeypatch):
    profile = {"target_language_code": "es", "proficiency_level": "A1"}
    context = resolve_language_context("es")
    draft = PostgresWorkflowRepository._analysis_draft(
        SimpleNamespace(mode="lesson", analysis_draft=None),
        profile,
        SimpleNamespace(objects=[], relations=[], action_suggestions=[], price_suggestions=[]),
    )
    assert draft["languageContext"] == context.snapshot()
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "missing/*")
    restored = operation_context("lesson", profile, draft["languageContext"])
    assert restored.pack_json == context.pack_json
    assert restored.display == context.display
    provider = MockTranslationProvider()
    translator(provider).translate(payload(runtime), language_context=restored)
    sent = json.loads(provider.requests[0].user_content)["language_context"]["context"]
    assert sent["fingerprint"] == context.display.fingerprint
    # Saved local experimental selection never becomes production approval.
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="unavailable"):
        operation_context("lesson", profile, draft["languageContext"])


def test_profile_code_casing_preserves_pack_locale(pack_dir, runtime):
    manifest = pack_dir / "pack.toml"
    manifest.write_text(
        manifest.read_text("utf-8").replace('code = "es"', 'code = "es-MX"'),
        "utf-8",
    )
    context = operation_context("lesson", {"target_language_code": "es-mx"})
    assert context.display.language_code == "es-MX"
    assert context.display.locale == "es-ES"  # Explicit pack preference is authoritative.
    request = {**payload(runtime), "targetLanguage": "es-mx"}
    translator(MockTranslationProvider()).translate(request, language_context=context)
    restored = operation_context("lesson", {"target_language_code": "es-mx"}, context.snapshot())
    assert restored.display == context.display
