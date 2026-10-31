import json
import tomllib
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from bundled_packs import bundled_pack
from test_language_pack_m01_regression import _grading_scenarios

from app.ai.cache.cache import ResultCache
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.language_packs.capabilities import mission_capability
from app.language_packs.evaluation import (
    evaluate_pack,
    evaluation_identity,
    evidence_is_current,
)
from app.language_packs.generation import (
    ApprovedVocabulary,
    BoundSceneFacts,
    assess,
    fact_id,
)
from app.language_packs.lessons.m01 import check_lesson as validate_assembled_lesson
from app.language_packs.model_source import ModelSource
from app.language_packs.pipeline import PipelineFailure, generate_pilot

SAMPLES = Path(__file__).parents[1] / "app/language_packs/samples/es-ES"
PACK_DIR = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


def _reference_pack():
    # Explicit propose=False demos compare legacy finite choices. This fixture
    # is not loaded by normal generation or production pack discovery.
    reference = Path(__file__).parent / "fixtures/language_packs/es-reference-parity.toml"
    return bundled_pack(PACK_DIR).model_copy(update={
        "lexical": tomllib.loads(reference.read_text("utf-8"))["lexical"],
    })


class FakeTextClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        return TextModelResponse(
            output_text=json.dumps(response, ensure_ascii=False),
            model_name="scripted-test",
            prompt_version=request.prompt_version,
        )


def _scene(level):
    value = json.loads((SAMPLES / "scene.json").read_text(encoding="utf-8"))
    return value, value["plan_specs"][level]


def _vocabulary():
    return ApprovedVocabulary.model_validate_json(
        (SAMPLES / "vocabulary.json").read_text(encoding="utf-8")
    )


def _source(level, responses=None):
    values = responses or [
        json.loads((SAMPLES / f"responses-{level}.json").read_text(encoding="utf-8"))
    ]
    client = FakeTextClient(values)
    return ModelSource(
        client,
        TextModelConfig(model_name="scripted-test"),
        mode="scripted responses (not a live model)",
        propose=False,
    ), client


def _candidate_response(candidates):
    return {
        "candidates": [
            {
                "slot_id": slot_id,
                "spec_id": spec_id,
                "text": text,
                "translation": translation or "Translation supplied by the builder.",
            }
            for slot_id, spec_id, text, translation in candidates
        ]
    }


def _builder_vocabulary(base, object_rows, attribute_rows=(), include_other=False):
    object_by_fact = {
        fact_id(
            "object",
            row["source"] if "source" in row else row["englishLabel"],
        ): row
        for row in object_rows
    }
    attributes_by_value = {
        row["value"]: row["key"] for row in attribute_rows
    }
    terms = []
    for term in base.terms:
        if term.fact_id in object_by_fact:
            row = object_by_fact[term.fact_id]
            item_id = row.get("vocabularyItemId")
            if item_id is not None:
                item_id = UUID(str(item_id))
            terms.append(term.model_copy(update={
                "vocabulary_item_id": item_id,
            }))
        elif term.term_id in attributes_by_value:
            terms.append(term.model_copy(update={
                "fact_id": attributes_by_value[term.term_id],
            }))
        elif include_other:
            terms.append(term)
    return base.model_copy(update={"terms": terms})




def _text_fields(result):
    fields = []
    for question in result.questions:
        correct = question.correct_text
        if correct is None and question.correct_option_id is not None:
            correct = next(
                option.label for option in question.options
                if option.option_id == question.correct_option_id
            )
        fields.append({
            "prompt": question.prompt,
            "options": [(option.option_id, option.label) for option in question.options],
            "correct": correct,
            "token_bank": Counter(question.token_bank),
            "translation": question.translation,
        })
    return fields




@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_scripted_router_generation_passes_existing_lesson_builders(level):
    pack = _reference_pack()
    scene, plan_specs = _scene(level)
    facts = BoundSceneFacts.model_validate(scene["facts"])
    vocabulary = _vocabulary()
    source, client = _source(level)

    generated = generate_pilot(
        pack,
        level,
        facts,
        vocabulary,
        source,
        plan_specs=plan_specs,
    )

    assert generated.assurance == "languageValidator"
    assert generated.mode.startswith("validated (scripted responses")
    assert generated.payload["pilotMode"] == "validated"
    assert generated.result is not None
    assert generated.task is not None
    validate_assembled_lesson(level, generated.result, generated.approved, pack)
    assert all(
        item.assessment.status == "languageValidator"
        and item.assessment.passed is True
        for item in generated.sentences
    )
    expected = json.loads(
        (Path(__file__).parent / "fixtures/m01_spanish_structure.json").read_text(
            encoding="utf-8"
        )
    )[level]
    questions = generated.result.questions
    public_content = generated.task.public_content.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    answer_key = generated.task.answer_key.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    evaluations = {
        item.question_id: item
        for item in generated.task.answer_key.question_evaluations
    }
    assert generated.task.public_content.mission_id == expected["mission_id"]
    assert str(generated.task.public_content.practice_level) == expected["practice_level"]
    assert generated.task.public_content.content_version == expected["content_version"]
    assert len(questions) == expected["question_count"]
    assert [len(question.options) for question in questions] == (
        [2, 2, 2, 0] if level == "A1" else expected["option_counts"]
    )  # This explicit demo has two confirmed colours; runtime uses taught scene colours.
    assert set(public_content) == set(expected["public_content_keys"])
    support_shape = {
        key: len(value) if key == "prep" else value
        for key, value in public_content.items()
        if key in {"prep", "checkEachQuestion"}
    }
    assert support_shape == expected["support_shape"]
    assert [question.purpose for question in questions] == [
        item["purpose"] for item in expected["questions"]
    ]
    assert [question.interaction_type for question in questions] == [
        item["interaction_type"] for item in expected["questions"]
    ]
    assert list(Counter(question.section for question in questions).values()) == list(
        expected["section_counts"].values()
    )
    assert set(answer_key) == set(expected["answer_key"])
    assert _grading_scenarios(generated.task) == expected["grading"]
    for question, expected_question in zip(
        questions, expected["questions"], strict=True
    ):
        evaluation = evaluations[question.question_id]
        assert evaluation.target_ids == expected_question["target_ids"]
        assert evaluation.evidence_type == expected_question["evidence_type"]
        assert evaluation.rubric_criterion_ids == expected_question["criteria"]
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.json_schema_name == "language_pack_candidates_v1"
    assert request.prompt_version



def test_unreviewed_example_match_runs_validator_and_retains_match_metadata():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    source, _client = _source("A0")
    generated = generate_pilot(
        pack,
        "A0",
        BoundSceneFacts.model_validate(scene["facts"]),
        _vocabulary(),
        source,
        plan_specs=plan_specs,
    )

    matched = next(
        item for item in generated.sentences
        if item.candidate.spec_id == "build-identify-1-spec"
    ).assessment
    assert matched.status == "languageValidator"
    assert matched.passed is True
    assert matched.matched_example_id is not None
    assert matched.matched_review_status == "unreviewed"


def test_match_name_rejects_capitalization_and_terminal_punctuation():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    source, _client = _source("A0")
    generated = generate_pilot(
        pack,
        "A0",
        BoundSceneFacts.model_validate(scene["facts"]),
        _vocabulary(),
        source,
        plan_specs=plan_specs,
    )
    candidate = generated.sentences[0].candidate.model_copy(
        update={"text": "La taza."}
    )
    assessment = assess(candidate, pack, _vocabulary())

    assert assessment.status == "languageValidator"
    assert assessment.passed is False
    assert any("lower-case definite article" in message for message in assessment.messages)


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_evaluation_separates_structure_language_and_current_evidence(level):
    pack = _reference_pack()
    report, record = evaluate_pack(pack, level, _vocabulary())

    assert report["structural"]["valid_alternatives"] > 0
    assert report["linguistic"]["scope"].startswith("targeted checks")
    assert record.candidates_total == (
        report["structural"]["valid_alternatives"]
        + report["structural"]["rejects"]
    )
    assert evidence_is_current(pack, record, "M01", level, 1)

    capability = mission_capability(
        pack,
        ("M01", level, 1),
        evaluation_record=record,
        release_allowlist=[("es", "M01", level)],
    )
    assert capability.evaluation_current
    assert not capability.release_ready
    assert "fluent human review" in " ".join(capability.blockers)


def test_evaluation_identity_tracks_generation_content_and_validator_version():
    pack = _reference_pack()
    identity = evaluation_identity(pack, "A0")
    changed_constructions = [
        item.model_copy(update={"guidance": item.guidance + "\nExtra guidance."})
        if item.construction_id == "identify-object"
        else item
        for item in pack.constructions
    ]
    changed_pack = pack.model_copy(update={"constructions": changed_constructions})

    assert identity.generation_content_sha256 != evaluation_identity(
        changed_pack, "A0"
    ).generation_content_sha256
    assert identity.validator_versions == {
        "es": "es-targeted@7", "noun-phrase": "noun-phrase.v7", "pack-checks": "pack-checks.v1",
    }


def test_preview_generation_cannot_be_evaluation_evidence():
    pack = _reference_pack()

    with pytest.raises(ValueError, match="preview generation results"):
        evaluate_pack(
            pack,
            "A0",
            _vocabulary(),
            generation_result=SimpleNamespace(mode="experimentalPreview (scripted)"),
        )


def test_model_source_rejects_missing_specs_and_pipeline_surfaces_failure():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    source, _client = _source("A0", [{"candidates": []}])

    with pytest.raises(PipelineFailure, match="exactly one candidate"):
        generate_pilot(
            pack,
            "A0",
            BoundSceneFacts.model_validate(scene["facts"]),
            _vocabulary(),
            source,
            plan_specs=plan_specs,
        )


def test_generation_cache_reuses_routed_candidate_response():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    facts = BoundSceneFacts.model_validate(scene["facts"])
    source, client = _source("A0")
    cache = ResultCache()

    first = generate_pilot(
        pack, "A0", facts, _vocabulary(), source, plan_specs=plan_specs,
        cache=cache, preview=True,
    )
    second = generate_pilot(
        pack, "A0", facts, _vocabulary(), source, plan_specs=plan_specs,
        cache=cache, preview=True,
    )

    assert first.payload == second.payload
    assert len(client.requests) == 1


def test_repair_is_bounded_and_only_retries_the_failing_spec():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    initial = json.loads((SAMPLES / "responses-A0.json").read_text(encoding="utf-8"))
    initial["candidates"][2]["text"] = "Es un libro."
    repair = {
        "candidates": [
            {
                "slot_id": "buildIdentify-1",
                "spec_id": "build-identify-1-spec",
                "text": "Es una taza.",
                "translation": "It is a cup.",
            }
        ]
    }
    source, client = _source("A0", [initial, repair])

    generated = generate_pilot(
        pack,
        "A0",
        BoundSceneFacts.model_validate(scene["facts"]),
        _vocabulary(),
        source,
        plan_specs=plan_specs,
        max_repairs=1,
        preview=True,
    )

    repair_request = json.loads(client.requests[1].user_content)
    assert generated.assurance == "languageValidator"
    assert len(repair_request["specs"]) == 1
    assert repair_request["specs"][0]["spec_id"] == "build-identify-1-spec"
    assert repair_request["repair"]["buildIdentify-1/build-identify-1-spec"]
    assert "Es un libro." in repair_request["repair"]["buildIdentify-1/build-identify-1-spec"][0]


def test_repair_budget_exhaustion_reports_exact_failure():
    pack = _reference_pack()
    scene, plan_specs = _scene("A0")
    initial = json.loads((SAMPLES / "responses-A0.json").read_text(encoding="utf-8"))
    initial["candidates"][2]["text"] = "Es un libro."
    failed_repair = {
        "candidates": [
            {
                "slot_id": "buildIdentify-1",
                "spec_id": "build-identify-1-spec",
                "text": "Es un libro.",
                "translation": "It is a book.",
            }
        ]
    }
    source, client = _source("A0", [initial, failed_repair])

    with pytest.raises(PipelineFailure, match="role 'object' expects"):
        generate_pilot(
            pack,
            "A0",
            BoundSceneFacts.model_validate(scene["facts"]),
            _vocabulary(),
            source,
            plan_specs=plan_specs,
            max_repairs=1,
            preview=True,
        )

    assert len(client.requests) == 2
