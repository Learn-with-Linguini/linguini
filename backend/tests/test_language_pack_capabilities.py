import shutil
from pathlib import Path

from app.ai.features.learning_tasks import mission_a0, mission_a2, mission_m01
from app.language_packs.capabilities import lesson_plan, mission_capability
from app.language_packs.evaluation import EvaluationRecord, evaluation_identity
from app.language_packs.loader import load_mission_catalog, load_pack
from app.language_packs.schema import Provenance

FIXTURE = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


def _human_reviewed_pack(pack):
    reviewed = Provenance(
        source="test-only reviewer confirmation",
        review_status="humanReviewed",
        reviewers=["reviewer"],
    )
    constructions = []
    for construction in pack.constructions:
        constructions.append(
            construction.model_copy(
                update={
                    "provenance": reviewed,
                    "examples": [
                        item.model_copy(update={"provenance": reviewed})
                        for item in construction.examples
                    ],
                    "mistakes": [
                        item.model_copy(update={"provenance": reviewed})
                        for item in construction.mistakes
                    ],
                }
            )
        )
    return pack.model_copy(
        update={
            "provenance": reviewed,
            "labels": [
                item.model_copy(update={"provenance": reviewed}) for item in pack.labels
            ],
            "constructions": constructions,
        }
    )


def test_catalog_loads_and_preserves_current_mission_purpose_order():
    from typing import get_args

    from app.ai.features.learning_tasks import (
        mission_m02,
        mission_m03,
        mission_m04,
        mission_m05,
        mission_m06,
    )

    catalog = load_mission_catalog()
    expected = {
        ("M01", "A0"): mission_a0.ORDERS["M01"] * 2,
        ("M01", "A1"): mission_m01._ORDER,
        ("M01", "A2"): mission_a2._EXPECTED["M01"],
        ("M02", "A0"): mission_a0.ORDERS["M02"] * 2,
        ("M02", "A1"): mission_m02._ORDER,
        ("M02", "A2"): mission_a2._EXPECTED["M02"],
        ("M03", "A0"): mission_a0.ORDERS["M03"] * 2,
        ("M03", "A1"): mission_m03._ORDER,
        ("M03", "A2"): mission_a2._EXPECTED["M03"],
        # dev's A0 situation questions have no purposes; three sentence slots feed all six.
        ("M04", "A0"): ["askOwnership", "answerOwnership", "sayOwnedObject"],
        ("M04", "A1"): mission_m04._ORDER,
        ("M04", "A2"): mission_a2._EXPECTED["M04"],
        ("M05", "A0"): ["askPreference", "sayPreference", "sayChoice"],
        ("M05", "A1"): mission_m05._ORDER,
        # dev's M06 question purposes, declared in order on its question model.
        ("M06", "A2"): list(get_args(mission_m06.M06Question.model_fields["purpose"].annotation)),
    }
    for template in catalog.missions:
        key = (template.mission_id, template.practice_level.value)
        plan = lesson_plan(load_pack(FIXTURE), (*key, template.content_version))
        assert [slot.purpose for slot in plan.slots] == expected[key]


def test_capability_reports_support_but_blocks_unreviewed_fixture_from_release():
    pack = load_pack(FIXTURE)
    capability = mission_capability(
        pack,
        ("M01", "A0", 1),
        release_allowlist=[("es", "M01", "A0")],
    )

    assert capability.supported
    assert not capability.release_enabled
    assert "pack" in capability.unreviewed_items
    assert capability.missing_constructions == []


def test_release_requires_support_reviewed_material_evidence_and_allowlist(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("LINGUINI_LANGUAGE_PACK_RELEASES", raising=False)
    pack_dir = tmp_path / "es-ES" / "everyday"
    pack_dir.parent.mkdir()
    shutil.copytree(FIXTURE, pack_dir)
    pack = _human_reviewed_pack(load_pack(pack_dir))
    without_evidence = mission_capability(
        pack,
        ("M01", "A1", 1),
        release_allowlist=[("es", "M01", "A1")],
    )
    identity = evaluation_identity(pack, "A1").model_copy(update={"thresholds_met": True})
    evidence = EvaluationRecord(
        identity=identity,
        cases_total=1,
        candidates_total=1,
        structural_passed=1,
        linguistic_passed=1,
        linguistic_assessed=1,
        valid_alternatives=1,
        valid_alternatives_accepted=1,
        rejects=0,
        rejects_structurally=0,
        rejects_linguistically=0,
        missed_rejects=0,
        thresholds_met=True,
    )
    allowed = mission_capability(
        pack,
        ("M01", "A1", 1),
        release_allowlist=[("es", "M01", "A1")],
        evaluation_record=evidence.model_dump(mode="json", by_alias=False),
    )
    not_allowed = mission_capability(
        pack,
        ("M01", "A1", 1),
        evaluation_record=evidence.model_dump(mode="json", by_alias=False),
    )

    assert allowed.supported
    assert allowed.unreviewed_items == []
    assert allowed.release_enabled
    assert not not_allowed.release_enabled
    assert not without_evidence.release_enabled
    assert "no evaluation evidence" in without_evidence.blockers


def test_capability_reports_missing_and_outdated_constructions():
    pack = load_pack(FIXTURE)
    missing = pack.model_copy(
        update={
            "constructions": [
                construction for construction in pack.constructions
                if construction.construction_id != "identify-object"
            ]
        }
    )
    outdated = pack.model_copy(
        update={
            "constructions": [
                construction.model_copy(update={"version": 0})
                if construction.construction_id == "identify-object"
                else construction
                for construction in pack.constructions
            ]
        }
    )

    assert mission_capability(missing, ("M01", "A0", 1)).missing_constructions == [
        "identify-object"
    ]
    assert mission_capability(outdated, ("M01", "A0", 1)).outdated_constructions == [
        "identify-object"
    ]


def test_plan_slots_keep_targets_labels_bindings_and_stable_ids():
    plan = lesson_plan(
        load_pack(FIXTURE),
        ("M01", "A0", 1),
        {"confirmName-1": {"identity": "object:cup"}},
    )
    confirm = plan.slots[1]

    assert confirm.slot_id == "confirmName-1"
    assert confirm.target_ids == ["identify-object"]
    assert confirm.required_labels == ["yes-answer", "no-answer"]
    assert confirm.bindings == {"identity": "object:cup"}

    a1_plan = lesson_plan(load_pack(FIXTURE), ("M01", "A1", 1))
    assert [slot.slot_id for slot in a1_plan.slots] == [
        "confirmObject-1",
        "confirmObject-2",
        "chooseAttribute",
        "describeObject",
    ]
