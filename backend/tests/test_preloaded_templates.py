"""Precomputed scene templates: generation, reuse, fallback and script controls.

Mocked text providers only — no network. Templates are made with the target language's
pack: a translation stage makes the translation and its meaning review (two calls).
"""

import json
from uuid import uuid4

import pytest
from test_ispy_clue_service import clues
from test_learning_task_service import response_body, tasks

from app.ai.cache import GENERATED_CONTENT_KEY, TemplateMissing, TemplateSet
from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.ispy_clues import ISpyClueService
from app.ai.features.learning_tasks import LearningTaskResult, LearningTaskService
from app.ai.features.translation import SceneTranslationService
from app.ai.observability import NoOpAITracer
from app.language_packs.context import resolve_language_context
from app.repositories.postgres.workflow import ispy_clue_payload, learning_task_payload
from app.schemas.media import MediaAsset
from app.scripts import precompute_preloaded_scenes as script
from app.scripts.preloaded_templates import (
    CallBudget,
    CallCountingTracer,
    curated_generation_inputs,
    generate_row_templates,
)

ITEMS = [
    {
        "id": "cup", "translation": "cup", "wordClass": "noun",
        "marker": 1, "x": 20, "y": 30, "attributes": {"color": "red"},
    },
    {
        "id": "table", "translation": "table", "wordClass": "noun",
        "marker": 2, "x": 50, "y": 70, "attributes": {},
    },
]
RELATIONS = [{"subjectItemId": "cup", "relation": "on", "referenceItemId": "table"}]
RESERVE = {"translation": 2, "lessons": 2, "clues": 2}
# Translation (with its review, so twice its reserve), lessons and clues.
FULL_BUDGET = 2 * RESERVE["translation"] + RESERVE["lessons"] + RESERVE["clues"]
STAGES = ["pack-translation", "pack-lessons", "pack-clues"]


def media_asset(**overrides) -> MediaAsset:
    values = {
        "media_type": "image", "source": "preloaded",
        "storage_key": f"test/{uuid4()}", "mime_type": "image/jpeg",
    }
    return MediaAsset(**{**values, **overrides})


def scene_row(asset=None, slug=None) -> dict:
    asset = asset or media_asset()
    slug = slug or f"test-{uuid4()}"
    content = script.build_scene_content(
        slug=slug, title="Desk",
        description="A red cup is on a table.", difficulty="beginner",
        media_asset=asset, items=[dict(item) for item in ITEMS], relations=RELATIONS,
    )
    return {
        "id": script.scene_row_id(slug), "slug": slug, "title": "Desk",
        "description": "A red cup is on a table.",
        "difficulty": "beginner", "sort_order": 99, "media_asset_id": asset.id,
        "is_active": True, "content": content,
    }


def _remap(text: str, payload: dict) -> str:
    keys = {
        row["source"].removeprefix("the "): row["key"]
        for row in payload["objects"]
    }
    if not {"cup", "table"} <= keys.keys():
        return "{}"
    for old, new in [
        ("object_1:color", payload["attributes"][0]["key"]),
        ("object_1", keys["cup"]),
        ("object_2", keys["table"]),
        ("relation_1", payload["relationships"][0]["key"]),
    ]:
        text = text.replace(json.dumps(old), json.dumps(new))
    return text


# Requests a pack lesson makes; the multilingual tests' mock answers them.
PACK_SCHEMAS = frozenset({
    "language_pack_candidates_v1", "language_vocabulary_proposals", "language_content_review",
})


def _pack_translation(payload):
    """A pack-guided translation: each noun with its own article, gender and display."""
    from test_language_pack_multilingual import LEXICON

    lex = LEXICON[payload.get("targetLanguage", "es").lower()]

    def colour(value):
        forms = lex["colours"].get(value)
        return (forms if isinstance(forms, str) else forms[0]) if forms else value

    def row(field, item):
        source = item["source"]
        if field == "objects":
            # Re-grounded labels may read "the cup"; the noun is still a cup.
            noun, article, gender = lex["nouns"].get(
                source.removeprefix("the "), (source, None, None),
            )
            return dict(key=item["key"], source=source, translation=noun, article=article,
                        gender=gender, native_display=" ".join(filter(None, [article, noun])))
        translation = (colour(source) if field == "attributes"
                       else lex["relations"].get(source, source))
        return dict(key=item["key"], source=source, translation=translation,
                    native_display=translation)

    return json.dumps({
        field: [row(field, item) for item in payload.get(field, [])]
        for field in ("objects", "attributes", "relationships")
    }, ensure_ascii=False)


class SceneModel:
    """A mocked provider answering translation, lesson and clue requests.

    Pack lessons (the only mission lessons) are answered by the multilingual tests'
    deterministic pack mock, in the requested language.
    """

    def __init__(self, error=None) -> None:
        self.requests = []
        self.error = error
        self.pack_providers = {}

    def _pack(self, request):
        from test_language_pack_multilingual import MockPackProvider

        content = json.loads(request.user_content)
        language = (content.get("language") or {}).get("code", "es")
        provider = self.pack_providers.setdefault(language, MockPackProvider(language))
        return provider.generate(request)

    def generate(self, request, **_):
        self.requests.append(request.json_schema_name)
        if self.error is not None:
            raise self.error
        if request.json_schema_name in PACK_SCHEMAS:
            return self._pack(request)
        # A repair request appends prose and the rejected response after the payload.
        payload = json.JSONDecoder().raw_decode(request.user_content)[0]
        if request.json_schema_name == "scene_translation_v1":
            body = _pack_translation(payload)
        elif request.json_schema_name == "pack_translation_review":
            body = json.dumps({"issues": []})
        elif request.json_schema_name == "learning_tasks_v2":
            body = _remap(response_body(LearningTaskResult.model_validate(tasks())), payload)
        else:
            body = _remap(json.dumps(clues()), payload)
        return TextModelResponse(
            output_text=body, model_name="test-text-model",
            prompt_version=request.prompt_version, input_tokens=10, output_tokens=10,
        )


def services(model) -> dict:
    options = {"tracer": NoOpAITracer(), "provider": "openai"}
    cfg = TextModelConfig(model_name="test-text-model", max_retries=1)
    return {
        "translation": SceneTranslationService(model, cfg, **options),
        "lessons": LearningTaskService(model, cfg, **options),
        "clues": ISpyClueService(model, cfg, **options),
    }


def unlimited() -> CallBudget:
    return CallBudget(None, CallCountingTracer())


def precomputed_row() -> dict:
    row = scene_row()
    outcomes = generate_row_templates(row, "es", services(SceneModel()), unlimited(), RESERVE)
    assert [outcome.status for outcome in outcomes] == ["generated"] * 3
    return row


def run_session(row, model, session_id=None, edit=None):
    """Translate, lesson and clue calls as one learner session makes them."""
    payload, objects, relations = curated_generation_inputs(row, "es", session_id or uuid4())
    if edit:
        payload = edit(payload)
    templates = TemplateSet.from_content([row["content"]])
    feature = services(model)
    translated = feature["translation"].translate(
        payload, templates=templates, language_context=resolve_language_context("es"),
    )
    lessons = feature["lessons"].generate(
        learning_task_payload(payload, translated, relations), templates=templates
    )
    found = feature["clues"].generate(
        ispy_clue_payload(payload, translated, objects, relations), templates=templates
    )
    return objects, translated, lessons, found


def test_unchanged_scene_reuses_templates_with_new_references_and_no_calls():
    row = precomputed_row()
    stored = row["content"][GENERATED_CONTENT_KEY]
    assert {entry["feature"] for entry in stored["templates"]} == {
        "sceneTranslation", "learningTask", "ispyClue",
    }
    assert all(entry["language"] == "es" for entry in stored["templates"])
    assert "object_1" not in json.dumps(stored)

    model = SceneModel(error=AssertionError("provider must not be called"))
    objects, translated, lessons, found = run_session(row, model)
    assert model.requests == []
    keys = {str(obj.id) for obj in objects}
    assert {term.key for term in translated.objects} == keys
    assert {clue.answer_object_key for clue in found.clues} == keys
    assert {
        key for task in lessons.tasks for question in task.questions
        for key in question.object_keys
    } <= keys


def test_edited_scene_falls_back_to_routed_generation():
    row = precomputed_row()
    model = SceneModel()

    def recolour(payload):
        payload["attributes"][0]["source"] = "blue"
        return payload

    run_session(row, model, edit=recolour)
    assert model.requests[0] == "scene_translation_v1"
    assert len(model.requests) >= 3


def test_stale_variant_is_regenerated_and_old_variant_kept():
    row = precomputed_row()
    for entry in row["content"][GENERATED_CONTENT_KEY]["templates"]:
        entry["variant"] = "old-prompt|old-schema|old-validator"
    model = SceneModel()
    outcomes = generate_row_templates(row, "es", services(model), unlimited(), RESERVE)
    assert [outcome.status for outcome in outcomes] == ["generated"] * 3
    assert len(model.requests) == 4
    assert len(row["content"][GENERATED_CONTENT_KEY]["templates"]) == 6


def test_regrounded_labels_regenerate_stale_templates_with_provider_budget():
    row = scene_row()
    for item in row["content"]["items"]:
        item["translation"] = f"the {item['translation']}"
    generate_row_templates(
        row, "es", services(SceneModel()), unlimited(), RESERVE
    )
    old_fingerprints = {
        entry["feature"]: entry["fingerprint"]
        for entry in row["content"][GENERATED_CONTENT_KEY]["templates"]
    }
    for item in row["content"]["items"]:
        item["translation"] = item["translation"].removeprefix("the ")

    model = SceneModel()
    budget = CallBudget(FULL_BUDGET, CallCountingTracer())
    outcomes = generate_row_templates(row, "es", services(model), budget, RESERVE)

    assert [outcome.status for outcome in outcomes] == ["generated"] * 3
    assert len(model.requests) == 4
    new_fingerprints = {
        entry["feature"]: entry["fingerprint"]
        for entry in row["content"][GENERATED_CONTENT_KEY]["templates"]
    }
    assert old_fingerprints.keys() == new_fingerprints.keys()
    assert all(old_fingerprints[key] != new_fingerprints[key] for key in old_fingerprints)


def test_rerun_resumes_from_stored_templates_without_calls():
    row = precomputed_row()
    model = SceneModel()
    outcomes = generate_row_templates(row, "es", services(model), unlimited(), RESERVE)
    assert [outcome.status for outcome in outcomes] == ["reused"] * 3
    assert model.requests == []


def test_force_regenerates_only_selected_stage():
    row = precomputed_row()
    model = SceneModel()
    outcomes = generate_row_templates(
        row, "es", services(model), unlimited(), RESERVE,
        stages=frozenset({"lessons"}), force=True,
    )
    assert [outcome.status for outcome in outcomes] == ["reused", "generated", "reused"]
    assert model.requests == ["learning_tasks_v2"]


def test_call_cap_reports_missing_templates_without_calls():
    row = scene_row()
    model = SceneModel()
    outcomes = generate_row_templates(
        row, "es", services(model), CallBudget(0, CallCountingTracer()), RESERVE
    )
    assert [(outcome.status, outcome.reason) for outcome in outcomes] == [
        ("missing", "callBudget"),
        ("missing", "translationMissing"),
        ("missing", "translationMissing"),
    ]
    assert model.requests == []
    assert GENERATED_CONTENT_KEY not in row["content"]


def test_template_set_without_generation_raises_instead_of_calling():
    row = scene_row()
    payload, _, _ = curated_generation_inputs(row, "es")
    model = SceneModel()
    with pytest.raises(TemplateMissing):
        services(model)["translation"].translate(
            payload, templates=TemplateSet(generate=False),
            language_context=resolve_language_context("es"),
        )
    assert model.requests == []


def test_failure_report_has_codes_only(tmp_path):
    row = scene_row()
    error = ProviderError(
        ProviderErrorCode.PROVIDER_UNAVAILABLE, "upstream body sk-secret-123 about cup"
    )
    outcomes = generate_row_templates(row, "es", services(SceneModel(error)), unlimited(), RESERVE)
    assert outcomes[0].status == "failed"
    path = tmp_path / "report.json"
    script.write_report(path, outcomes, unlimited(), dry_run=True)
    text = path.read_text()
    report = json.loads(text)
    assert report["summary"] == {"failed": 1, "missing": 2}
    assert report["outcomes"][0]["reason"] == ProviderErrorCode.PROVIDER_UNAVAILABLE.value
    assert "sk-secret" not in text and "cup" not in text


def test_json_artifact_keeps_server_only_templates(tmp_path):
    row = precomputed_row()
    asset = media_asset()
    row["media_asset_id"] = asset.id
    path = tmp_path / "rows.json"
    script.write_json_artifact(path, [row], [asset])
    rows, _, failures = script.load_json_artifact(path)
    assert failures == 0
    assert rows[0]["content"][GENERATED_CONTENT_KEY] == row["content"][GENERATED_CONTENT_KEY]


def test_from_json_dry_run_checks_templates_without_calls(tmp_path, monkeypatch):
    asset = media_asset()
    row = scene_row(asset)
    source = tmp_path / "rows.json"
    script.write_json_artifact(source, [row], [asset])
    model = SceneModel()
    monkeypatch.setattr(script, "_template_services", lambda *_: services(model))
    report = tmp_path / "report.json"
    state = tmp_path / "state.json"
    args = [
        "--from-json", str(source), "--dry-run", "--slug", row["slug"], "--language", "es",
        "--report", str(report), "--state", str(state), "--env-file", str(tmp_path / "none"),
    ]
    assert script.main(args) == 0
    assert model.requests == []
    assert json.loads(report.read_text())["outcomes"][0]["reason"] == "callBudget"

    assert script.main([*args, "--max-provider-calls", str(FULL_BUDGET)]) == 0
    assert len(model.requests) == 4
    stored, _, _ = script.load_json_artifact(state)
    assert GENERATED_CONTENT_KEY in stored[0]["content"]

    model.requests.clear()
    assert script.main([*args, "--max-provider-calls", str(FULL_BUDGET)]) == 0
    assert model.requests == []
    statuses = {o["status"] for o in json.loads(report.read_text())["outcomes"]}
    assert statuses == {"reused"}


def test_reground_cli_updates_json_rows_without_scene_analysis(tmp_path, monkeypatch):
    from app.ai.features.object_grounding import GroundedBox

    asset = media_asset()
    row = scene_row(asset)
    for item in row["content"]["items"]:
        item["translation"] = f"the {item['translation']}"
    generate_row_templates(
        row, "es", services(SceneModel()), unlimited(), RESERVE
    )
    source = tmp_path / "input.json"
    script.write_json_artifact(source, [row], [asset])
    output = tmp_path / "output.json"
    report = tmp_path / "report.json"

    class FakeGrounder:
        def __init__(self):
            self.calls = []

        def ground_instances(self, image, labels, *, threshold=None):
            assert image.data == b"image bytes"
            self.calls.append((labels, threshold))
            if threshold is None and labels == ["cup"]:
                return {
                    "cup": [
                        GroundedBox(
                            x=0.1, y=0.2, width=0.1, height=0.1, score=0.9
                        )
                    ]
                }
            if threshold == 0.27 and labels == ["table"]:
                return {
                    "table": [
                        GroundedBox(
                            x=0.5, y=0.2, width=0.1, height=0.1, score=0.3
                        )
                    ]
                }
            return {}

    grounder = FakeGrounder()

    class FakeStorage:
        def __init__(self, *_):
            pass

        def download(self, _storage_key):
            return b"image bytes"

    monkeypatch.setattr(script, "build_object_grounder", lambda _settings: grounder)
    monkeypatch.setattr(script, "ImageStorage", FakeStorage)
    template_model = SceneModel()
    monkeypatch.setattr(
        script, "_template_services", lambda *_: services(template_model)
    )
    monkeypatch.setattr(
        script,
        "build_uploaded_scene_analyzer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("scene analysis must not run")
        ),
    )

    assert script.main(
        [
            "--from-json",
            str(source),
            "--reground",
            "--reground-fallback-threshold",
            "0.27",
            "--dry-run",
            "--max-provider-calls",
            str(FULL_BUDGET),
            "--language",
            "es",
            "--json",
            str(output),
            "--report",
            str(report),
            "--slug",
            row["slug"],
            "--env-file",
            str(tmp_path / "none"),
        ]
    ) == 0

    updated_rows, _assets, failures = script.load_json_artifact(output)
    assert failures == 0
    assert grounder.calls == [
        (["cup"], None),
        (["table"], None),
        (["table"], 0.27),
    ]
    assert [item["translation"] for item in updated_rows[0]["content"]["items"]] == [
        "cup",
        "table",
    ]
    assert len(template_model.requests) == 4
    result = json.loads(report.read_text())
    assert result["outcomes"][0] == {
        "slug": row["slug"],
        "language": "",
        "stage": "grounding",
        "status": "generated",
    }
    assert [
        (outcome["stage"], outcome["status"])
        for outcome in result["outcomes"][1:]
    ] == [(stage, "generated") for stage in STAGES]


def test_a_language_without_a_ready_pack_gets_no_templates():
    row = scene_row()
    model = SceneModel()
    outcomes = generate_row_templates(row, "xx", services(model), unlimited(), RESERVE)
    assert [(outcome.stage, outcome.status, outcome.reason) for outcome in outcomes] == [
        (stage, "missing", "noLanguagePack") for stage in STAGES
    ]
    assert model.requests == []
    assert GENERATED_CONTENT_KEY not in row["content"]


def test_one_scene_row_keeps_templates_for_every_target_language():
    row = scene_row()
    for language in ("es", "fr"):
        outcomes = generate_row_templates(
            row, language, services(SceneModel()), unlimited(), RESERVE
        )
        assert [outcome.status for outcome in outcomes] == ["generated"] * 3
        assert {outcome.language for outcome in outcomes} == {language}
    stored = row["content"][GENERATED_CONTENT_KEY]["templates"]
    assert {(entry["feature"], entry["language"]) for entry in stored} == {
        (feature, language)
        for feature in ("sceneTranslation", "learningTask", "ispyClue")
        for language in ("es", "fr")
    }
    rerun = generate_row_templates(row, "fr", services(SceneModel()), unlimited(), RESERVE)
    assert [outcome.status for outcome in rerun] == ["reused"] * 3
