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
from app.ai.features.translation.schemas import SceneTranslationResult
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
    def __init__(self, missing=None, overrides=None, review=None):
        self.requests = []
        self.reviews = []
        self.missing = missing
        self.overrides = overrides or {}
        self.review = review or (lambda terms: {"issues": []})

    def generate(self, request):
        if request.json_schema_name == "pack_translation_review":
            self.reviews.append(request)
            output = self.review(json.loads(request.user_content)["terms"])
            return TextModelResponse(
                output_text=output if isinstance(output, str) else json.dumps(output),
                model_name="mocked-reviewer", prompt_version=request.prompt_version,
            )
        self.requests.append(request)
        # A repair request appends instructions after the original JSON.
        data, _ = json.JSONDecoder().raw_decode(request.user_content)
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
                if len(self.requests) == 1:
                    noun = self.overrides.get(row["source"], noun)
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


def translator(provider, cache=None, retries=0):
    return SceneTranslationService(
        provider,
        TextModelConfig(model_name="mocked-Spanish", max_retries=retries),
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


def test_a_language_without_a_pack_is_not_translated(pack_dir, runtime):
    # The configured folder holds only the Spanish pack.
    assert resolve_language_context("it") is None
    provider = MockTranslationProvider()
    with pytest.raises(SceneTranslationError, match="ready pack"):
        translator(provider).translate(
            payload(runtime), language_context=resolve_language_context("it"),
        )
    assert provider.requests == [] and not provider.reviews


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


def _flag(source, suggestion, meaning="something else"):
    """A mock meaning review flagging every translation of ``source``."""
    def review(terms):
        return {"issues": [
            {"group": term["group"], "key": term["key"], "currentMeaning": meaning,
             "suggestion": suggestion, "problem": f"Use {suggestion}."}
            for term in terms if term["source"] == source
        ]}
    return review


def _flag_cup(terms):
    return {"issues": [
        {"group": term["group"], "key": term["key"], "currentMeaning": "white vegetable",
         "suggestion": "taza", "problem": "Use taza."}
        for term in terms if term["source"] == "cup" and term["translation"] != "taza"
    ]}


def test_meaning_review_sends_a_mistranslation_back_for_repair(pack_dir, runtime):
    context = resolve_language_context("es")
    provider = MockTranslationProvider(overrides={"cup": "verdura blanca"}, review=_flag_cup)
    translated = translator(provider, retries=1).translate(
        payload(runtime), language_context=context
    )
    assert [term.translation for term in translated.objects if term.source == "cup"] == ["taza"]
    assert len(provider.requests) == 2 and len(provider.reviews) == 2
    repair = provider.requests[1].user_content
    assert '\\"cup\\" as \\"la verdura blanca\\" means \\"white vegetable\\": use taza.' in repair


def test_changed_word_still_flagged_after_repair_fails_before_cards(pack_dir, runtime):
    context = resolve_language_context("es")
    provider = MockTranslationProvider(overrides={"cup": "verdura blanca"},
                                       review=_flag("cup", "copa"))
    with pytest.raises(SceneTranslationError, match="unusable output"):
        translator(provider, retries=1).translate(payload(runtime), language_context=context)
    assert len(provider.requests) == 2


def test_word_the_translator_keeps_after_repair_is_left_to_content_review(pack_dir, runtime):
    context = resolve_language_context("es")
    provider = MockTranslationProvider(review=_flag("cup", "copa"))
    translated = translator(provider, retries=1).translate(
        payload(runtime), language_context=context
    )
    # The models disagree: the word is kept rather than failing the session.
    assert [term.translation for term in translated.objects if term.source == "cup"] == ["taza"]
    assert len(provider.requests) == 2


@pytest.mark.parametrize("review", [
    _flag("cup", "taza"),  # suggests the word already used
    _flag("cup", "copa", meaning="cup"),  # says the word already means its source
    _flag("cup", "copa", meaning="cup; mug"),  # names the source among the word's senses
])
def test_self_contradicting_flags_are_ignored(pack_dir, runtime, review):
    context = resolve_language_context("es")
    provider = MockTranslationProvider(review=review)
    translated = translator(provider, retries=1).translate(
        payload(runtime), language_context=context
    )
    assert translated.objects and len(provider.requests) == 1


@pytest.mark.parametrize("source,translation,suggestion,meaning", [
    ("under", "கீழே", "கீழ்", "below; down; underneath in a general sense"),
    ("on", "மேல", "மேல்", "top; upper side; above"),
])
def test_reported_tamil_form_preferences_do_not_fail_meaning_review(
    source, translation, suggestion, meaning,
):
    def review(terms):
        return {"issues": [
            {"group": "relationships", "key": term["key"], "issueType": "formPreference",
             "currentMeaning": meaning, "suggestion": suggestion,
             "problem": "Prefer the relational root to the adverbial or colloquial form."}
            for term in terms if term["group"] == "relationships"
        ]}

    provider = MockTranslationProvider(review=review)
    translated = SceneTranslationResult(objects=[], attributes=[], relationships=[{
        "key": "relation-form", "source": source, "translation": translation,
        "nativeDisplay": translation, "article": None, "gender": None,
        "romanization": "keezhe" if source == "under" else "mela",
    }])
    # Replay the exact review stage independently of vocabulary-card script checks.
    context = SimpleNamespace(
        display=SimpleNamespace(model_dump=lambda **kwargs: {"locale": "ta-IN"}),
        pack=SimpleNamespace(variety=SimpleNamespace(
            model_dump=lambda **kwargs: {"register": "everyday"},
        )),
    )
    translator(provider, retries=0)._review_meaning(
        {"sceneTitle": "Objects", "targetLanguage": "ta"}, translated, context, {},
    )
    assert translated.relationships[0].translation == translation
    assert len(provider.reviews) == 1 and not provider.requests


def test_form_preference_does_not_consume_translation_repair(pack_dir, runtime):
    def review(terms):
        issues = _flag("on", "encima de", meaning="on top")(terms)["issues"]
        return {"issues": [{**issue, "issueType": "formPreference"} for issue in issues]}

    provider = MockTranslationProvider(review=review)
    result = translator(provider, retries=0).translate(
        payload(runtime), language_context=resolve_language_context("es"),
    )
    assert result.relationships[0].translation == "sobre"
    assert len(provider.requests) == 1


def test_wrong_relation_meaning_still_requires_repair(pack_dir, runtime):
    provider = MockTranslationProvider(overrides={"on": "debajo de"},
                                       review=_flag("on", "sobre", meaning="underneath"))
    with pytest.raises(SceneTranslationError, match="unusable output"):
        translator(provider, retries=0).translate(
            payload(runtime), language_context=resolve_language_context("es"),
        )


def test_a_reviewer_going_in_circles_keeps_the_repaired_word(pack_dir, runtime):
    def review(terms):
        # First it suggests taza; once taza is used, it suggests copa instead.
        return {"issues": [
            {"group": term["group"], "key": term["key"],
             "currentMeaning": "white vegetable" if term["translation"] != "taza" else "dish",
             "suggestion": "taza" if term["translation"] != "taza" else "copa",
             "problem": "Use another word."}
            for term in terms if term["source"] == "cup"
        ]}

    context = resolve_language_context("es")
    provider = MockTranslationProvider(overrides={"cup": "verdura blanca"}, review=review)
    translated = translator(provider, retries=1).translate(
        payload(runtime), language_context=context
    )
    assert [term.translation for term in translated.objects if term.source == "cup"] == ["taza"]
    assert len(provider.requests) == 2


@pytest.mark.parametrize("answer", ["not json", {"issues": [
    {"group": "objects", "key": "not-a-supplied-key", "currentMeaning": "x",
     "suggestion": "y", "problem": "Unknown."}
]}])
def test_unusable_or_unanchored_review_keeps_the_translation(pack_dir, runtime, answer):
    context = resolve_language_context("es")
    provider = MockTranslationProvider(review=lambda terms: answer)
    translated = translator(provider).translate(payload(runtime), language_context=context)
    assert translated.objects and len(provider.requests) == 1


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
    translated = translator(MockTranslationProvider()).translate(
        payload(runtime), language_context=resolve_language_context("es"),
    )
    # A task saved before language contexts existed has none.
    intro, _ = cards(None, runtime, translated)
    serialized = intro.model_dump_json()
    assert "languageContext" not in serialized
    assert "romanization" not in serialized
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
def test_missions_come_only_from_the_pack_context(pack_dir, runtime, level):
    context = resolve_language_context("es")
    profile = {"target_language_code": "es", "proficiency_level": level}
    # Without a pack context there are no mission lessons: legacy builders are gone.
    assert lesson_missions("lesson", profile, None) == []
    planned = lesson_missions("lesson", profile, context)
    assert planned and all(context.is_ready(mission) for mission in planned)


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
