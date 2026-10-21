"""Mission-generic pack plumbing: readiness per mission, ownership, facts and the registry."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.language_packs.capabilities import mission_template_key, pack_mission_keys
from app.language_packs.context import LanguageContext, resolve_language_context
from app.language_packs.lessons import PACK_MISSION_IDS, pack_mission
from app.language_packs.loader import load_pack
from app.language_packs.plan import bind_plan
from app.language_packs.runtime import session_inputs
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import lesson_missions

PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


@pytest.fixture
def packs_on(monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACK))


def _context(ready=(), declared=()):
    return LanguageContext("{}", "{}", (), True, tuple(ready), tuple(declared))


def _ids(missions):
    return [(mission.mission_id, str(mission.practice_level)) for mission in missions]


def test_catalog_templates_resolve_through_the_registry():
    assert PACK_MISSION_IDS == {"M01", "M02", "M03"}
    assert pack_mission_keys() == [
        ("M01", "A0", 1), ("M01", "A1", 1), ("M01", "A2", 1),
        ("M02", "A0", 1), ("M02", "A1", 2), ("M02", "A2", 1),
        ("M03", "A0", 1), ("M03", "A1", 1), ("M03", "A2", 1),
    ]
    # Templates match dev's mission definitions (M02 A1 lessons are content version 2).
    assert mission_template_key("M02", "A1") == ("M02", "A1", 2)
    with pytest.raises(ValueError, match="no pack lesson implementation"):
        pack_mission("M04")


def test_context_records_ready_and_declared_missions(packs_on):
    context = resolve_language_context("es")
    assert context.ready_missions == (
        "M01:A0:1", "M01:A1:1", "M01:A2:1", "M02:A0:1", "M02:A1:2", "M02:A2:1",
        "M03:A0:1", "M03:A1:1", "M03:A2:1",
    )
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
    # M02 and M03 have pack implementations but are not ready here: not offered.
    assert not {"M02", "M03"} & {mission_id for mission_id, _ in _ids(missions)}
    assert {"M04", "M05"} <= {mission_id for mission_id, _ in _ids(missions)}


def test_declared_but_blocked_missions_never_fall_back_to_legacy():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context([], ["M01:A1:1"]))
    assert "M01" not in {mission.mission_id for mission in missions}


def test_pack_missions_never_use_their_legacy_builder_when_packs_are_on():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context(["M01:A0:1"], ["M01:A0:1"]))
    ids = {mission_id for mission_id, _ in _ids(missions)}
    assert not ids & {"M01", "M02", "M03"}
    # Missions without a pack implementation keep their legacy builders.
    assert {"M04", "M05"} <= ids


def test_pack_only_languages_get_every_ready_pack_mission():
    profile = {"proficiency_level": "A2", "target_language_code": "ta"}
    ready = ["M01:A2:1", "M02:A2:1"]
    missions = lesson_missions(SessionMode.LESSON, profile, _context(ready, ready))
    assert _ids(missions) == [("M01", "A2"), ("M02", "A2")]


def test_m02_a2_photo_rule_needs_one_object_matching_both_clues():
    from app.language_packs.lessons.m02 import photo_reasons
    from app.missions import get_mission
    from app.services.mission_eligibility import scene_attributes

    mission = get_mission("M02", "A2", 1)
    cup, table, book = (
        SimpleNamespace(id=UUID(int=n), label=label, attributes=attrs)
        for n, label, attrs in (
            (1, "cup", {"color": "red"}), (2, "table", {}), (3, "book", {"color": "red"}),
        )
    )
    on = SimpleNamespace(id=UUID(int=9), subject_scene_object_id=cup.id,
                         reference_scene_object_id=table.id, relation="on")
    assert photo_reasons(mission, [cup, table, book], [on], scene_attributes) == []
    # Both red objects on the table: the clues no longer identify one object.
    book_on = SimpleNamespace(id=UUID(int=10), subject_scene_object_id=book.id,
                              reference_scene_object_id=table.id, relation="on")
    assert photo_reasons(mission, [cup, table, book], [on, book_on], scene_attributes)


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
        bind_plan(pack, "A1", facts, vocabulary, mission_id="M04")


def _counted_cups(quantity, label="cup"):
    objects = [SimpleNamespace(id=UUID(int=i), label=label, attributes={}) for i in (1, 2)]
    return objects, [{"sceneObjectIds": [str(UUID(int=1))], "quantity": quantity}]


@pytest.mark.parametrize("level,quantity,eligible", [
    ("A0", 3, True), ("A0", 5, False), ("A2", 3, False),
])
def test_m03_photo_rules(level, quantity, eligible):
    from app.language_packs.lessons.m03 import photo_reasons
    from app.missions import get_mission
    from app.services.mission_eligibility import scene_attributes

    objects, groups = _counted_cups(quantity)
    reasons = photo_reasons(get_mission("M03", level, 1), objects, [], scene_attributes,
                            counted_groups=groups)
    assert (reasons == []) is eligible


def test_m03_a2_needs_two_groups_of_different_objects_and_counts():
    from app.language_packs.lessons.m03 import photo_reasons
    from app.missions import get_mission
    from app.services.mission_eligibility import scene_attributes

    cup, book = (SimpleNamespace(id=UUID(int=n), label=label, attributes={})
                 for n, label in ((1, "cup"), (2, "book")))
    mission = get_mission("M03", "A2", 1)

    def reasons(*groups):
        return photo_reasons(mission, [cup, book], [], scene_attributes, counted_groups=[
            {"sceneObjectIds": [str(obj.id)], "quantity": quantity} for obj, quantity in groups
        ])

    assert reasons((cup, 3), (book, 5)) == []
    assert reasons((cup, 3), (book, 3)), "equal counts cannot be compared"
    assert reasons((cup, 3), (cup, 5)), "the groups must be different objects"


def test_m03_count_terms_take_the_counted_noun_form():
    from app.language_packs.lessons.m03 import number_vocabulary

    pack = load_pack(PACK)
    objects = [SimpleNamespace(id=UUID(int=1), label="apple", attributes={})]
    words = [SimpleNamespace(id=UUID(int=11))]
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=1)), source="apple", translation="manzana",
                                 article="la", gender="feminine")],
        attributes=[], relationships=[],
    )
    for quantity, written in ((1, "una"), (3, "tres")):
        groups = [{"sceneObjectIds": [str(UUID(int=1))], "quantity": quantity}]
        facts, vocabulary = session_inputs(pack, objects, [], words, translated, {}, groups)
        terms = {term.fact_id: term for term in number_vocabulary(pack, facts, vocabulary).terms}
        assert terms["count:1"].target_text == written
        assert terms["count:1"].part_of_speech == "determiner"
        # Every pack number is available for fictional counts and practice boards.
        assert {f"number:{n}" for n in range(1, 11)} <= terms.keys()


def test_one_word_can_realize_the_article_and_the_number_one():
    from app.language_packs.generation import _shared_word_use
    from app.language_packs.lessons.m03 import number_vocabulary

    pack = load_pack(PACK)
    objects = [SimpleNamespace(id=UUID(int=1), label="apple", attributes={})]
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=1)), source="apple", translation="manzana",
                                 article="la", gender="feminine")],
        attributes=[], relationships=[],
    )
    facts, vocabulary = session_inputs(pack, objects, [], [SimpleNamespace(id=UUID(int=11))],
                                       translated, {})
    vocabulary = number_vocabulary(pack, facts, vocabulary)
    assert _shared_word_use("una manzana", vocabulary, "number:1", "determiner")
    assert _shared_word_use("dos manzanas", vocabulary, "number:1", "determiner") is None


def test_m02_positions_fall_back_to_other_confirmed_relations():
    from app.language_packs.lessons.m02 import _relation_alternatives

    pack = load_pack(PACK)
    labels = {1: ("cup", "taza"), 2: ("table", "mesa"), 3: ("book", "libro")}
    objects = [SimpleNamespace(id=UUID(int=n), label=label, attributes={})
               for n, (label, _text) in labels.items()]
    relations = [
        SimpleNamespace(id=UUID(int=20), subject_scene_object_id=UUID(int=1),
                        reference_scene_object_id=UUID(int=2), relation="on"),
        SimpleNamespace(id=UUID(int=21), subject_scene_object_id=UUID(int=3),
                        reference_scene_object_id=UUID(int=2), relation="nextTo"),
    ]
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=n)), source=label, translation=text,
                                 article="la", gender="feminine")
                 for n, (label, text) in labels.items()],
        attributes=[],
        relationships=[SimpleNamespace(key=str(UUID(int=20)), source="on", translation="sobre"),
                       SimpleNamespace(key=str(UUID(int=21)), source="next to",
                                       translation="al lado de")],
    )
    words = [SimpleNamespace(id=UUID(int=n + 10)) for n in labels]
    facts, vocabulary = session_inputs(pack, objects, relations, words, translated, {})
    on = next(rel for rel in facts.scene_facts.relations if rel.relation == "on")
    # No model proposals: the photo's other relation still gives a false position.
    assert [(kind, term.target_text) for kind, term in
            _relation_alternatives(on, facts, vocabulary)] == [("next_to", "al lado de")]
