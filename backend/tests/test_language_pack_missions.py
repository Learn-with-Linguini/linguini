"""Mission-generic pack plumbing: readiness per mission, ownership, facts and the registry."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.language_packs.capabilities import mission_template_key, pack_mission_keys
from app.language_packs.context import LanguageContext, resolve_language_context
from app.language_packs.loader import load_pack
from app.language_packs.plan import bind_plan
from app.language_packs.registry import PACK_MISSIONS, pack_mission
from app.language_packs.runtime import session_inputs
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import lesson_missions

PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


@pytest.fixture
def packs_on(monkeypatch):
    monkeypatch.setenv("LINGUINI_M01_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACK))


def _context(ready=(), declared=()):
    return LanguageContext("{}", "{}", (), True, tuple(ready), tuple(declared))


def _ids(missions):
    return [(mission.mission_id, str(mission.practice_level)) for mission in missions]


def test_catalog_templates_resolve_through_the_registry():
    assert set(PACK_MISSIONS) == {"M01"}
    assert pack_mission_keys() == [("M01", "A0", 1), ("M01", "A1", 1), ("M01", "A2", 1)]
    assert mission_template_key("M01", "A1") == ("M01", "A1", 1)
    with pytest.raises(ValueError, match="no pack lesson implementation"):
        pack_mission("M02")


def test_context_records_ready_and_declared_missions(packs_on):
    context = resolve_language_context("es")
    assert context.ready_missions == ("M01:A0:1", "M01:A1:1", "M01:A2:1")
    assert context.declared_missions == context.ready_missions
    assert context.ready_levels == ("A0", "A1", "A2")
    snapshot = context.snapshot()
    assert snapshot["readyMissions"] == list(context.ready_missions)
    assert LanguageContext.from_snapshot(snapshot).ready_missions == context.ready_missions


def test_snapshots_saved_before_multi_mission_packs_load_as_m01(packs_on):
    snapshot = resolve_language_context("es").snapshot()
    snapshot.pop("readyMissions")
    snapshot.pop("declaredMissions")
    snapshot["readyLevels"] = ["A1"]
    restored = LanguageContext.from_snapshot(snapshot)
    assert restored.ready_missions == ("M01:A1:1",)
    # Old sessions always routed M01 to the pack, so every M01 level stays pack-owned.
    assert all(restored.declares("M01", level) for level in ("A0", "A1", "A2"))


def test_ready_pack_missions_replace_legacy_versions_first():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(
        SessionMode.LESSON, profile, _context(["M01:A1:1"], ["M01:A1:1"])
    )
    assert _ids(missions)[0] == ("M01", "A1")
    assert [mission_id for mission_id, _ in _ids(missions)].count("M01") == 1
    assert {"M02", "M03", "M04", "M05"} <= {mission_id for mission_id, _ in _ids(missions)}


def test_declared_but_blocked_missions_never_fall_back_to_legacy():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context([], ["M01:A1:1"]))
    assert "M01" not in {mission.mission_id for mission in missions}


def test_undeclared_missions_keep_their_legacy_builder():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context(["M01:A0:1"], ["M01:A0:1"]))
    assert ("M01", "A1") in _ids(missions)


def test_counted_groups_become_facts_only_for_confirmed_objects():
    pack = load_pack(PACK)
    objects = [SimpleNamespace(id=UUID(int=i), label="cup", attributes={}) for i in (1, 2, 3)]
    words = [SimpleNamespace(id=UUID(int=i + 10)) for i in (1, 2, 3)]
    translated = SimpleNamespace(
        objects=[
            SimpleNamespace(key=str(obj.id), source="cup", translation="taza", article="la",
                            gender="feminine")
            for obj in objects
        ],
        attributes=[], relationships=[],
    )
    groups = [
        {"sceneObjectIds": [str(UUID(int=1)), str(UUID(int=2))], "quantity": 2},
        {"sceneObjectIds": [str(UUID(int=99))], "quantity": 1},
        {"sceneObjectIds": [str(UUID(int=3))], "quantity": 25},
    ]
    facts, _ = session_inputs(pack, objects, [], words, translated, {}, groups)
    (count,) = facts.scene_facts.counted_groups
    assert count.quantity == 2
    assert count.object_fact_ids == [f"object:{UUID(int=1)}", f"object:{UUID(int=2)}"]
    assert count.fact_id in facts.all_fact_ids


def test_bind_plan_rejects_missions_without_a_pack_implementation():
    pack = load_pack(PACK)
    facts, vocabulary = session_inputs(
        pack, [], [], [], SimpleNamespace(objects=[], attributes=[], relationships=[]), {},
    )
    with pytest.raises(ValueError, match="no pack lesson implementation"):
        bind_plan(pack, "A1", facts, vocabulary, mission_id="M02")
