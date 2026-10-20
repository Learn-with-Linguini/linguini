import json
import tomllib
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
import test_mission_a0
import test_mission_m01
import test_missions_a2
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
from app.language_packs.loader import load_pack
from app.language_packs.model_source import ModelSource
from app.language_packs.pipeline import PipelineFailure, generate_pilot
from app.missions import get_mission
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m01_a2_task
from app.services.mission_lessons_m01 import m01_lesson_task
from app.services.mission_registry import A2_MISSION_LESSONS

SAMPLES = Path(__file__).parents[1] / "app/language_packs/samples/es-ES"
PACK_DIR = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


def _reference_pack():
    # Explicit propose=False demos compare legacy finite choices. This fixture
    # is not loaded by normal generation or production pack discovery.
    reference = Path(__file__).parent / "fixtures/language_packs/es-reference-parity.toml"
    return load_pack(PACK_DIR).model_copy(update={
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


def _parity_scenario(level, monkeypatch):
    base_scene = json.loads((SAMPLES / "scene.json").read_text(encoding="utf-8"))
    plan_specs = json.loads(json.dumps(base_scene["plan_specs"][level]))
    if level == "A0":
        counter = iter(range(1, 100))
        monkeypatch.setattr(test_mission_a0, "uuid4", lambda: UUID(int=next(counter)))
        mission, spec, builder_payload, _objects = test_mission_a0._lesson("M01", "es")
        builder_result = spec.generation.fallback(builder_payload)
        by_key = {row["key"]: row for row in builder_payload["approvedObjects"]}
        focus = [by_key[key] for key in builder_payload["focus"]]
        facts = BoundSceneFacts(scene_facts={
            "objects": [
                {
                    "fact_id": fact_id("object", row["source"]),
                    "scene_object_id": row["key"],
                    "label": row["source"],
                    "marker": row["marker"],
                }
                for row in builder_payload["approvedObjects"]
            ],
        })
        vocabulary = _builder_vocabulary(
            _vocabulary(), builder_payload["approvedObjects"]
        )
        vocabulary_ids = {
            row["key"]: next(
                term.vocabulary_item_id for term in vocabulary.terms
                if term.fact_id == fact_id("object", row["source"])
            )
            for row in builder_payload["approvedObjects"]
        }
        candidates = []
        for index, (name, confirm, identify) in enumerate(
            zip(builder_result.questions[::3], builder_result.questions[1::3],
                builder_result.questions[2::3], strict=True),
            1,
        ):
            target = focus[index - 1]
            named = next(row for row in by_key.values() if row["isIt"] == confirm.prompt)
            plan_specs[f"matchName-{index}"][0]["bindings"] = {
                "object": fact_id("object", target["source"]),
            }
            confirm_spec = plan_specs[f"confirmName-{index}"][0]
            confirm_spec["bindings"] = {
                "object": fact_id("object", named["source"]),
                "shown": fact_id("object", target["source"]),
            }
            confirm_spec["truth"] = confirm.statement_true
            plan_specs[f"buildIdentify-{index}"][0]["bindings"] = {
                "object": fact_id("object", target["source"]),
            }
            candidates.extend([
                (
                    f"matchName-{index}",
                    plan_specs[f"matchName-{index}"][0]["spec_id"],
                    name.prompt,
                    builder_payload["approvedTranslations"].get(
                        name.prompt, "The object."
                    ),
                ),
                (
                    f"confirmName-{index}",
                    confirm_spec["spec_id"],
                    confirm.prompt,
                    builder_payload["approvedTranslations"].get(
                        confirm.prompt, "Is this the object?"
                    ),
                ),
                (
                    f"buildIdentify-{index}",
                    plan_specs[f"buildIdentify-{index}"][0]["spec_id"],
                    identify.correct_text,
                    builder_payload["approvedTranslations"].get(
                        identify.correct_text, "This is the object."
                    ),
                ),
        ])
        from app.language_packs.lessons.common import DEMO_SESSION_ID as _SESSION_ID
        baseline_task = a0_lesson_task(
            _SESSION_ID, mission, builder_payload, builder_result,
            vocabulary_ids,
        )
        builder_selection = {
            "focus": list(builder_payload["focus"]),
            "markers": {
                row["key"]: row["marker"]
                for row in builder_payload["approvedObjects"]
            },
            "seed": builder_payload["seed"],
            "layout": {
                "statementCorrect": [
                    builder_result.questions[1].statement_true,
                    builder_result.questions[4].statement_true,
                ],
            },
        }
        return (
            facts, vocabulary, plan_specs, _candidate_response(candidates),
            builder_result, baseline_task, builder_payload, builder_selection,
        )

    if level == "A1":
        builder_payload = test_mission_m01.build("es", session_id=UUID(int=202))
        builder_result = test_mission_m01.fallback_m01_lesson(builder_payload)
        pairs = builder_payload["pairs"]
        object_rows = [
            {
                "source": pair["source"],
                "englishLabel": pair["source"],
                "key": pair["key"],
                "vocabularyItemId": pair["vocabularyItemId"],
            }
            for pair in pairs
        ]
        attribute_rows = [
            {
                "key": pair["attributeKey"],
                "objectKey": pair["key"],
                "objectFactId": fact_id("object", pair["source"]),
                "kind": pair["attributeType"],
                "value": pair["attributeSource"],
            }
            for pair in pairs
        ]
        table = {
            "source": "table",
            "englishLabel": "table",
            "key": test_mission_m01.TABLE,
            "vocabularyItemId": test_mission_m01.TABLE,
        }
        object_rows.append(table)
        attribute_rows.append({
            "key": f"{test_mission_m01.TABLE}:color",
            "objectKey": test_mission_m01.TABLE,
            "objectFactId": fact_id("object", "table"),
            "kind": "colour",
            "value": "white",
        })
        facts = BoundSceneFacts(scene_facts={
            "objects": [
                {
                    "fact_id": fact_id("object", row["source"]),
                    "scene_object_id": row["key"],
                    "label": row["source"],
                    "marker": index,
                }
                for index, row in enumerate(object_rows, 1)
            ],
            "attributes": [
                {
                    "fact_id": row["key"],
                    "object_fact_id": row["objectFactId"],
                    "kind": row["kind"],
                    "value": row["value"],
                }
                for row in attribute_rows
            ],
        })
        vocabulary = _builder_vocabulary(_vocabulary(), object_rows, attribute_rows)
        for index, pair in enumerate(pairs):
            slot_specs = plan_specs[f"confirmObject-{index + 1}"]
            question = builder_result.questions[index]
            named = next(
                candidate for candidate in pairs
                if candidate["nounPhrase"] in question.prompt
                or candidate["nounPhrase"].replace("una ", "la ").replace("un ", "el ")
                in question.prompt
            )
            truth = builder_payload["layout"]["statementCorrect"][index]
            shown_fact = fact_id("object", pair["source"])
            named_fact = fact_id("object", named["source"])
            other_fact = fact_id("object", pairs[1 - index]["source"])
            slot_specs[0]["bindings"] = {"object": named_fact, "shown": shown_fact}
            slot_specs[0]["truth"] = truth
            slot_specs[1]["bindings"] = {"object": shown_fact, "shown": shown_fact}
            slot_specs[1]["truth"] = truth
            slot_specs[1]["labels"] = ["yes"] if truth else ["no"]
            slot_specs[2]["bindings"] = {
                "object": named_fact if not truth else other_fact,
                "shown": shown_fact,
            }
            slot_specs[2]["truth"] = not truth
            slot_specs[2]["labels"] = ["no"] if truth else ["yes"]
        plan_specs["chooseAttribute"][0]["bindings"] = {
            "object": fact_id("object", pairs[0]["source"]),
            "attribute": pairs[0]["attributeKey"],
        }
        plan_specs["describeObject"][0]["bindings"] = {
            "object": fact_id("object", pairs[1]["source"]),
            "attribute": pairs[1]["attributeKey"],
        }
        candidates = []
        for index, question in enumerate(builder_result.questions[:2], 1):
            correct = next(
                option.label for option in question.options
                if option.option_id == question.correct_option_id
            )
            contrast = next(option.label for option in question.options if option.label != correct)
            candidates.extend([
                (f"confirmObject-{index}", f"confirm-object-{index}-prompt",
                 question.prompt, "Is this the object?"),
                (f"confirmObject-{index}", f"confirm-object-{index}-answer",
                 correct, "This is the shown object."),
                (f"confirmObject-{index}", f"confirm-object-{index}-contrast",
                 contrast, "This is the other object."),
            ])
        candidates.extend([
            ("chooseAttribute", "choose-attribute-answer",
             f"Es {pairs[0]['nounPhrase']} {pairs[0]['agreedForm']}.",
             "It is the described object."),
            ("describeObject", "describe-object-answer",
             builder_result.questions[3].correct_text,
             builder_result.questions[3].translation),
        ])
        from app.language_packs.lessons.common import DEMO_SESSION_ID as _SESSION_ID
        baseline_task = m01_lesson_task(
            _SESSION_ID, test_mission_m01.MISSION, builder_payload, builder_result,
            {pair["key"]: pair["vocabularyItemId"] for pair in pairs},
        )
        builder_selection = {
            "pairs": [
                {
                    "object_key": pair["key"],
                    "attribute_key": pair["attributeKey"],
                }
                for pair in pairs
            ],
            "layout": builder_payload["layout"],
        }
        return (
            facts, vocabulary, plan_specs, _candidate_response(candidates),
            builder_result, baseline_task, builder_payload, builder_selection,
        )

    objects, words, relations, groups, translated, markers = test_missions_a2._scene()
    mission = get_mission("M01", "A2", 1)
    builder_spec = A2_MISSION_LESSONS["A2:M01"]
    builder_payload = builder_spec.payload(
        mission, "es", objects, relations, words, translated, groups, {},
        "parity-scene", review_markers=markers,
    )
    builder_result = builder_spec.generation.fallback(builder_payload)
    approved = builder_payload["approvedFacts"]
    selected_attribute = builder_payload["facts"]["attribute"]
    selected_object = next(
        row for row in approved["approvedObjects"]
        if str(row["key"]) == str(selected_attribute["objectKey"])
    )
    selected_attribute_fact_id = fact_id(
        "attribute",
        f"{selected_object['englishLabel']}:{selected_attribute['kind']}",
        selected_attribute["value"],
    )
    assert selected_attribute_fact_id == plan_specs["chooseSceneMarker"][0][
        "bindings"
    ]["attribute"]
    object_rows = []
    object_facts = []
    attribute_facts = []
    attribute_rows = []
    for obj, word in zip(objects, words, strict=True):
        object_fact_id = fact_id("object", obj.label)
        object_rows.append({
            "key": str(obj.id),
            "source": obj.label,
            "englishLabel": obj.label,
            "marker": markers[str(obj.id)],
            "vocabularyItemId": str(word.id),
        })
        object_facts.append({
            "fact_id": object_fact_id,
            "scene_object_id": obj.id,
            "label": obj.label,
            "marker": markers[str(obj.id)],
        })
        for source_kind, value in obj.attributes.items():
            kind = "colour" if source_kind == "color" else source_kind
            attribute_id = fact_id("attribute", f"{obj.label}:{kind}", value)
            attribute_facts.append({
                "fact_id": attribute_id,
                "object_fact_id": object_fact_id,
                "kind": kind,
                "value": value,
            })
            attribute_rows.append({
                "key": attribute_id,
                "value": value,
                "objectKey": str(obj.id),
            })
    base_vocabulary = _vocabulary()
    attributes_by_value = {}
    for row in attribute_rows:
        attributes_by_value.setdefault(row["value"], []).append(row)
    vocabulary_terms = []
    for term in base_vocabulary.terms:
        object_row = next(
            (
                row for row in object_rows
                if term.fact_id == fact_id("object", row["source"])
            ),
            None,
        )
        if object_row is not None:
            vocabulary_terms.append(term.model_copy(update={
                "vocabulary_item_id": UUID(object_row["vocabularyItemId"]),
            }))
        elif term.term_id in attributes_by_value:
            for index, attribute_row in enumerate(
                attributes_by_value[term.term_id], 1
            ):
                vocabulary_terms.append(term.model_copy(update={
                    "term_id": f"{term.term_id}-scene-{index}",
                    "fact_id": attribute_row["key"],
                }))
        else:
            vocabulary_terms.append(term)
    vocabulary = base_vocabulary.model_copy(update={"terms": vocabulary_terms})
    relation_facts = []
    for relation in relations:
        subject = next(obj for obj in objects if obj.id == relation.subject_scene_object_id)
        reference = next(
            obj for obj in objects
            if obj.id == relation.reference_scene_object_id
        )
        relation_facts.append({
            "fact_id": fact_id(
                "relation", subject.label, reference.label, relation.relation
            ),
            "subject_fact_id": fact_id("object", subject.label),
            "reference_fact_id": fact_id("object", reference.label),
            "relation": relation.relation,
        })
    facts = BoundSceneFacts(scene_facts={
        "objects": object_facts,
        "attributes": attribute_facts,
        "relations": relation_facts,
    })
    candidates = [
        ("chooseSceneMarker", "choose-scene-marker-fact1",
         builder_payload["facts"]["first"], "There is the first fact."),
        ("buildSceneFact", "build-scene-fact-fact2",
         builder_result.questions[1].correct_text, "The second fact."),
        ("chooseSceneDescription", "choose-scene-description-connected",
         builder_payload["facts"]["q3"], "The connected facts."),
        ("chooseSceneDescription", "choose-scene-description-wrong-attribute",
         builder_payload["facts"]["wrongOne"], "A wrong attribute."),
        ("chooseSceneDescription", "choose-scene-description-false-first",
         builder_payload["facts"]["falseFirst"], "A false first fact."),
        ("chooseSceneDescription", "choose-scene-description-wrong-existence",
         builder_payload["facts"]["wrongTwo"], "A wrong existence claim."),
        ("buildSceneDescription", "build-scene-description-fact1",
         builder_payload["facts"]["first"], "The first fact."),
        ("buildSceneDescription", "build-scene-description-fact2",
         builder_result.questions[1].correct_text, "The second fact."),
        ("buildSceneDescription", "build-scene-description-fact3",
         builder_payload["facts"]["third"], "The third fact."),
        ("followUpSceneFact", "follow-up-scene-fact-spec",
         builder_payload["facts"]["detailPrompt"], "A follow-up question."),
    ]
    from app.language_packs.lessons.common import DEMO_SESSION_ID as _SESSION_ID
    baseline_task = m01_a2_task(
        _SESSION_ID, mission, builder_payload, builder_result,
        {row["key"]: row["vocabularyItemId"] for row in approved["approvedObjects"]},
    )
    builder_selection = {
        "selection": {
            "attribute": selected_attribute_fact_id,
            "object": fact_id("object", selected_object["englishLabel"]),
            "third_object": plan_specs["chooseSceneDescription"][0][
                "bindings"
            ]["other-object"],
            "attribute_key": selected_attribute["key"],
            "relation_key": (
                approved["approvedRelationships"][0]["key"]
                if approved["approvedRelationships"] else None
            ),
        },
        "seed": builder_payload["seed"],
        "markers": {
            row["key"]: row["marker"]
            for row in approved["approvedObjects"]
        },
    }
    return (
        facts, vocabulary, plan_specs, _candidate_response(candidates),
        builder_result, baseline_task, builder_payload, builder_selection,
    )


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
def test_pilot_text_and_answer_key_match_existing_builder_scene(level, monkeypatch):
    pack = _reference_pack()
    (
        facts,
        vocabulary,
        plan_specs,
        response,
        expected,
        expected_task,
        builder_payload,
        builder_selection,
    ) = _parity_scenario(level, monkeypatch)
    source, client = _source(level, [response])
    generated = generate_pilot(
        pack,
        level,
        facts,
        vocabulary,
        source,
        plan_specs=plan_specs,
        builder_selection=builder_selection,
    )

    assert len(client.requests) == 1
    validate_assembled_lesson(level, generated.result, generated.approved, pack)
    assert _text_fields(generated.result) == _text_fields(expected)
    if level == "A0":
        assert set(generated.payload["approvedSentenceChunks"]) == set(
            builder_payload["approvedSentenceChunks"]
        )
    assert generated.task.answer_key.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"mission_state"}
    ) == expected_task.answer_key.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"mission_state"}
    )
    actual_supports = generated.task.public_content.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    expected_supports = expected_task.public_content.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    for key in ("prep", "checkEachQuestion"):
        assert actual_supports.get(key) == expected_supports.get(key)


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
        "es": "es-targeted@7", "noun-phrase": "noun-phrase.v1", "pack-checks": "pack-checks.v1",
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
