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
    assert PACK_MISSION_IDS == {"M01", "M02", "M03", "M04", "M05"}
    assert pack_mission_keys() == [
        ("M01", "A0", 1), ("M01", "A1", 1), ("M01", "A2", 1),
        ("M02", "A0", 1), ("M02", "A1", 2), ("M02", "A2", 1),
        ("M03", "A0", 1), ("M03", "A1", 1), ("M03", "A2", 1),
        ("M04", "A0", 1), ("M04", "A1", 1), ("M04", "A2", 1),
        ("M05", "A0", 1), ("M05", "A1", 1),
    ]
    # Templates match dev's mission definitions (M02 A1 lessons are content version 2).
    assert mission_template_key("M02", "A1") == ("M02", "A1", 2)
    with pytest.raises(ValueError, match="no pack lesson implementation"):
        pack_mission("M06")


def test_context_records_ready_and_declared_missions(packs_on):
    context = resolve_language_context("es")
    assert context.ready_missions == (
        "M01:A0:1", "M01:A1:1", "M01:A2:1", "M02:A0:1", "M02:A1:2", "M02:A2:1",
        "M03:A0:1", "M03:A1:1", "M03:A2:1", "M04:A0:1", "M04:A1:1", "M04:A2:1",
        "M05:A0:1", "M05:A1:1",
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
    profile = {"proficiency_level": "A2", "target_language_code": "es"}
    missions = lesson_missions(
        SessionMode.LESSON, profile, _context(["M01:A2:1"], ["M01:A2:1"])
    )
    assert _ids(missions)[0] == ("M01", "A2")
    assert [mission_id for mission_id, _ in _ids(missions)].count("M01") == 1
    # M02-M04 have pack implementations but are not ready here: not offered.
    assert not {"M02", "M03", "M04"} & {mission_id for mission_id, _ in _ids(missions)}
    assert "M06" in {mission_id for mission_id, _ in _ids(missions)}


def test_declared_but_blocked_missions_never_fall_back_to_legacy():
    profile = {"proficiency_level": "A1", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context([], ["M01:A1:1"]))
    assert "M01" not in {mission.mission_id for mission in missions}


def test_pack_missions_never_use_their_legacy_builder_when_packs_are_on():
    profile = {"proficiency_level": "A2", "target_language_code": "es"}
    missions = lesson_missions(SessionMode.LESSON, profile, _context(["M01:A0:1"], ["M01:A0:1"]))
    ids = {mission_id for mission_id, _ in _ids(missions)}
    assert not ids & {"M01", "M02", "M03", "M04", "M05"}
    # Missions without a pack implementation keep their legacy builders.
    assert "M06" in ids


def test_pack_only_languages_get_every_ready_pack_mission():
    profile = {"proficiency_level": "A2", "target_language_code": "pt"}
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
        bind_plan(pack, "A2", facts, vocabulary, mission_id="M06")


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


def _two_cabinets(*labels):
    """A scene with two cabinets: a name alone does not pick out one of them."""
    labels = labels or (("cabinet", "armario"), ("window", "ventana"), ("cabinet", "armario"))
    pack = load_pack(PACK)
    objects = [SimpleNamespace(id=UUID(int=n), label=label, attributes={})
               for n, (label, _text) in enumerate(labels, 1)]
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=n)), source=label, translation=text,
                                 article="el", gender="masculine")
                 for n, (label, text) in enumerate(labels, 1)],
        attributes=[], relationships=[],
    )
    words = [SimpleNamespace(id=UUID(int=n + 10)) for n in range(1, len(labels) + 1)]
    return pack, *session_inputs(pack, objects, [], words, translated, {})


def test_m01_a0_contrasts_objects_with_different_names():
    from app.language_packs.lessons.m01 import plan_lesson

    pack, facts, vocabulary = _two_cabinets()
    labels = {obj.fact_id: obj.label for obj in facts.scene_facts.objects}
    plan = plan_lesson(pack, "A0", facts, vocabulary, "seed")
    focus = [labels[plan[f"matchName-{i}"][0]["bindings"]["object"]] for i in (1, 2)]
    assert sorted(focus) == ["cabinet", "window"]
    for index in (1, 2):
        spec = plan[f"confirmName-{index}"][0]
        named, shown = (labels[spec["bindings"][role]] for role in ("object", "shown"))
        # A false "Is this a cabinet?" never points at the other cabinet.
        assert (named == shown) is spec["truth"]


def test_m01_a0_needs_two_names_not_two_objects():
    from app.language_packs.lessons.m01 import plan_lesson

    pack, facts, vocabulary = _two_cabinets(("cabinet", "armario"), ("cabinet", "armario"))
    with pytest.raises(ValueError, match="differently named"):
        plan_lesson(pack, "A0", facts, vocabulary, "seed")


def test_m02_a0_tasks_name_different_objects():
    from app.language_packs.lessons.m02 import _a0_focus

    _pack, facts, _vocabulary = _two_cabinets()
    for seed in ("a", "b", "c", "d"):
        pairs = _a0_focus(facts.scene_facts.objects, seed)
        assert sorted(target.label for target, _other in pairs) == ["cabinet", "window"]
        assert all(target.label != other.label for target, other in pairs)


def test_m03_a0_counts_the_first_of_several_small_groups():
    from app.language_packs.lessons.m03 import number_vocabulary, photo_reasons, plan_lesson
    from app.missions import get_mission
    from app.services.mission_eligibility import scene_attributes

    pack = load_pack(PACK)
    labels = {1: ("chair", "silla", "feminine"), 2: ("table", "mesa", "feminine")}
    objects = [SimpleNamespace(id=UUID(int=n), label=label, attributes={})
               for n, (label, _text, _gender) in labels.items()]
    groups = [{"sceneObjectIds": [str(UUID(int=1))], "quantity": 3},
              {"sceneObjectIds": [str(UUID(int=2))], "quantity": 2}]
    assert photo_reasons(get_mission("M03", "A0", 1), objects, [], scene_attributes,
                         counted_groups=groups) == []
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=n)), source=label, translation=text,
                                 article="la", gender=gender)
                 for n, (label, text, gender) in labels.items()],
        attributes=[], relationships=[],
    )
    words = [SimpleNamespace(id=UUID(int=n + 10)) for n in labels]
    facts, vocabulary = session_inputs(pack, objects, [], words, translated, {}, groups)
    vocabulary = number_vocabulary(pack, facts, vocabulary)
    plan = plan_lesson(pack, "A0", facts, vocabulary, "seed")
    counted = {spec["bindings"].get("count") for spec in plan["matchChunk-1"]} - {None}
    assert counted == {facts.scene_facts.counted_groups[0].fact_id}


def _owned_scene(language_pack=PACK, colours=("red", "white", "green")):
    """Cup, book and table, each with a colour; the shape M04 lessons plan from."""
    pack = load_pack(language_pack)
    labels = {1: ("cup", "taza", "feminine"), 2: ("book", "libro", "masculine"),
              3: ("table", "mesa", "feminine")}
    objects = [SimpleNamespace(id=UUID(int=n), label=label, attributes={"color": colour})
               for (n, (label, _text, _gender)), colour in zip(labels.items(), colours,
                                                                strict=True)]
    translated = SimpleNamespace(
        objects=[SimpleNamespace(key=str(UUID(int=n)), source=label, translation=text,
                                 article="la" if gender == "feminine" else "el", gender=gender)
                 for n, (label, text, gender) in labels.items()],
        attributes=[SimpleNamespace(key=f"{UUID(int=n)}:color", source=colour,
                                    translation={"red": "rojo", "white": "blanco",
                                                 "green": "verde"}[colour])
                    for n, colour in zip(labels, colours, strict=True)],
        relationships=[],
    )
    words = [SimpleNamespace(id=UUID(int=n + 10)) for n in labels]
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    facts, vocabulary = session_inputs(pack, objects, [], words, translated, markers)
    return pack, objects, markers, facts, vocabulary


def test_m04_owners_come_from_the_learner_choice_and_the_saved_roleplay():
    from app.language_packs.lessons.m04 import ownership_facts
    from app.language_packs.vocabulary import with_pack_vocabulary
    from app.missions import get_mission
    from app.services.mission_roleplay import assign_roleplay

    pack, objects, markers, facts, vocabulary = _owned_scene()
    vocabulary = with_pack_vocabulary(pack, vocabulary)
    learner = {"learner_facts": {"ownedObjectId": str(objects[1].id), "pretend": True}}
    (owner,) = ownership_facts(pack, "A0", facts, vocabulary, learner).scene_facts.owners
    assert (owner.object_fact_id, owner.owner, owner.fictional) == (
        f"object:{objects[1].id}", "first", True,
    )
    roleplay = assign_roleplay(get_mission("M04", "A1", 1), UUID(int=100), objects, markers)
    owners = ownership_facts(pack, "A1", facts, vocabulary,
                             {"roleplay_facts": roleplay}).scene_facts.owners
    # The saved role-play's learner, Ana and Leo become the pack's first, ana and leo.
    assert sorted(owner.owner for owner in owners) == ["ana", "first", "leo"]
    assert {owner.object_fact_id for owner in owners} == {
        obj.fact_id for obj in facts.scene_facts.objects
    }
    # No choice saved: no owner, and the A0 planner says what is missing.
    assert ownership_facts(pack, "A0", facts, vocabulary, {}).scene_facts.owners == []


def test_m04_a2_assigns_an_object_its_detail_tells_apart():
    from app.language_packs.lessons.m04 import ownership_facts
    from app.language_packs.vocabulary import with_pack_vocabulary

    pack, _objects, _markers, facts, vocabulary = _owned_scene()
    owners = ownership_facts(pack, "A2", facts, with_pack_vocabulary(pack, vocabulary),
                             {}).scene_facts.owners
    assert [owner.owner for owner in owners] == ["first", "ana"]
    # Every object the same colour: nothing tells the learner's object apart.
    pack, _objects, _markers, facts, vocabulary = _owned_scene(colours=("red",) * 3)
    assert ownership_facts(pack, "A2", facts, with_pack_vocabulary(pack, vocabulary),
                           {}).scene_facts.owners == []


@pytest.mark.parametrize("text,agrees", [
    ("La taza es mía.", True), ("Es mi taza.", True), ("La taza es mío.", False),
])
def test_m04_possessives_agree_with_the_owned_noun(text, agrees):
    from app.language_packs.generation import _owner_agreement
    from app.language_packs.lessons.m04 import ownership_facts, possessive_vocabulary
    from app.language_packs.vocabulary import with_pack_vocabulary

    pack, objects, _markers, facts, vocabulary = _owned_scene()
    vocabulary = with_pack_vocabulary(pack, vocabulary)
    facts = ownership_facts(pack, "A0", facts, vocabulary,
                            {"learner_facts": {"ownedObjectId": str(objects[0].id)}})
    vocabulary = possessive_vocabulary(pack, facts, vocabulary)
    (owner,) = facts.scene_facts.owners
    bindings = {"object": owner.object_fact_id, "owner": owner.fact_id}
    assert (_owner_agreement(text, bindings, vocabulary) == []) is agrees


def test_m04_photo_rules_need_the_learner_choice_and_a_telling_detail():
    from app.language_packs.lessons.m04 import CHOICE_REASON, photo_reasons
    from app.missions import get_mission
    from app.services.mission_eligibility import photo_eligibility, scene_attributes

    cup, book = (SimpleNamespace(id=UUID(int=n), label=label, attributes={"color": colour})
                 for n, label, colour in ((1, "cup", "red"), (2, "book", "red")))
    a0 = get_mission("M04", "A0", 1)
    assert photo_reasons(a0, [cup, book], [], scene_attributes,
                         mission_choices={"ownership": {}}) == [CHOICE_REASON]
    chosen = {"ownership": {"sceneObjectId": str(cup.id)}}
    assert photo_reasons(a0, [cup, book], [], scene_attributes, mission_choices=chosen) == []
    context = _context(["M04:A0:1"], ["M04:A0:1"])
    check = photo_eligibility(a0, [cup, book], (), (), {"ownership": {}}, context)
    # The learner still has to choose; the photo itself lacks nothing.
    assert check.missing == ("choices",)
    a2 = get_mission("M04", "A2", 1)
    assert photo_reasons(a2, [cup, book], [], scene_attributes)
    book.attributes = {"color": "blue"}
    assert photo_reasons(a2, [cup, book], [], scene_attributes) == []


def test_m05_likes_come_from_the_learner_choice_and_the_saved_roleplay():
    from app.language_packs.lessons.m05 import plan_lesson, preference_facts
    from app.language_packs.vocabulary import with_pack_vocabulary
    from app.missions import get_mission
    from app.services.mission_roleplay import assign_roleplay

    pack, objects, markers, facts, vocabulary = _owned_scene()
    vocabulary = with_pack_vocabulary(pack, vocabulary)
    choice = {"preference": {"sceneObjectIds": [str(objects[1].id), str(objects[0].id)],
                             "chosenObjectId": str(objects[1].id), "reaction": "like"}}
    a0 = preference_facts(pack, "A0", facts, vocabulary, {"learner_facts": choice})
    (mine,) = a0.scene_facts.preferences
    # The learner's own choice is real, and remembers what it was weighed against.
    assert (mine.object_fact_id, mine.person, mine.likes, mine.fictional) == (
        f"object:{objects[1].id}", "first", True, False,
    )
    assert mine.compared_fact_id == f"object:{objects[0].id}"
    plan = plan_lesson(pack, "A0", a0, vocabulary, "seed")
    assert [spec["use"] for spec in plan["sayPreference"]] == ["like", "dislike", "like"]
    assert [spec["truth"] for spec in plan["sayPreference"]] == [True, False, False]
    assert plan["sayPreference"][2]["bindings"]["object"] == f"object:{objects[0].id}"
    assert plan["sayChoice"] == []

    roleplay = assign_roleplay(get_mission("M05", "A1", 1), UUID(int=100), objects, markers)
    a1 = preference_facts(pack, "A1", facts, vocabulary, {"roleplay_facts": roleplay})
    likes = {fact.person: fact.likes for fact in a1.scene_facts.preferences}
    # dev's role-play: the learner and Leo like their objects, Ana does not.
    assert likes == {"first": True, "ana": False, "leo": True}
    plan = plan_lesson(pack, "A1", a1, vocabulary, "seed")
    choose = {spec["spec_id"]: (spec["use"], spec["truth"]) for spec in plan["choosePreference"]}
    assert choose == {
        "choosePreference-correct": ("like", True),
        "choosePreference-flipped": ("dislike", False),
        # Leo's like about another object keeps his polarity; only the object is wrong.
        "choosePreference-other": ("like", False),
    }
    their = [(spec["use"], spec["truth"]) for spec in plan["buildTheirPreference"]]
    assert their == [("question", True), ("dislike", True), ("like", False)]
    # No choice saved: no preference, and nothing to plan from.
    assert preference_facts(pack, "A0", facts, vocabulary, {}).scene_facts.preferences == []


def test_m05_dislike_choice_plans_what_the_learner_takes_instead():
    from app.language_packs.lessons.m05 import plan_lesson, preference_facts
    from app.language_packs.vocabulary import with_pack_vocabulary

    pack, objects, _markers, facts, vocabulary = _owned_scene()
    vocabulary = with_pack_vocabulary(pack, vocabulary)
    choice = {"preference": {"sceneObjectIds": [str(objects[0].id)], "reaction": "dislike"}}
    facts = preference_facts(pack, "A0", facts, vocabulary, {"learner_facts": choice})
    plan = plan_lesson(pack, "A0", facts, vocabulary, "seed")
    assert [spec["use"] for spec in plan["sayPreference"]] == ["like", "dislike", "dislike"]
    assert [spec["truth"] for spec in plan["sayPreference"]] == [False, True, False]
    taken, wrong = plan["sayChoice"]
    assert taken["bindings"]["object"] == f"object:{objects[1].id}" and taken["truth"]
    assert wrong["bindings"]["object"] == f"object:{objects[0].id}" and not wrong["truth"]


@pytest.mark.parametrize("like,dislike,phrase,expected", [
    ("Me gusta la taza.", "No me gusta la taza.", "la taza",
     ("___ la taza.", "Me gusta", "No me gusta")),
    ("저는 컵을 좋아해요.", "저는 컵을 안 좋아해요.", "컵을",
     ("저는 컵을 ___.", "좋아해요", "안 좋아해요")),
    # One chunk would be empty: the whole sentences are the choices.
    ("Ich mag die Tasse.", "Ich mag die Tasse nicht.", "die Tasse",
     ("___", "Ich mag die Tasse.", "Ich mag die Tasse nicht.")),
])
def test_m05_gap_is_the_side_of_the_noun_that_says_like(like, dislike, phrase, expected):
    from app.language_packs.lessons.m05 import preference_gap

    assert preference_gap(like, dislike, phrase) == expected


def test_m05_noun_phrases_are_what_two_same_frame_sentences_write_differently():
    from app.language_packs.lessons.m05 import differing_parts

    assert differing_parts("J'aime la tasse.", "J'aime l'assiette.") == ("la tasse", "l'assiette")
    assert differing_parts("Ich mag die Tasse.", "Ich mag den Teller.") == (
        "die Tasse", "den Teller",
    )
    assert differing_parts("저는 컵을 좋아해요.", "저는 책을 좋아해요.") == ("컵을", "책을")
    assert differing_parts("Me gusta la taza.", "Me gusta la taza.") is None


@pytest.mark.parametrize("use,text,passes", [
    ("like", "Me gusta la taza.", True),
    ("like", "No me gusta la taza.", False),
    ("dislike", "No me gusta la taza.", True),
    ("dislike", "Me gusta la taza.", False),
])
def test_m05_spec_use_sets_the_polarity_pack_checks_demand(use, text, passes):
    construction = next(item for item in load_pack(PACK).constructions
                        if item.construction_id == "my-preference")
    checks = [check for check in construction.checks if check.applies(use, True)]
    assert all(check.passes(text) for check in checks) is passes


def test_m05_photo_rule_needs_the_learner_choice():
    from app.language_packs.lessons.m05 import CHOICE_REASON, photo_reasons
    from app.missions import get_mission
    from app.services.mission_eligibility import photo_eligibility, scene_attributes

    cup, book = (SimpleNamespace(id=UUID(int=n), label=label, attributes={})
                 for n, label in ((1, "cup"), (2, "book")))
    a0 = get_mission("M05", "A0", 1)
    assert photo_reasons(a0, [cup, book], [], scene_attributes,
                         mission_choices={"preference": {}}) == [CHOICE_REASON]
    skipped = {"preference": {"sceneObjectIds": [str(cup.id)], "reaction": "skip"}}
    assert photo_reasons(a0, [cup, book], [], scene_attributes,
                         mission_choices=skipped) == [CHOICE_REASON]
    picked = {"preference": {"sceneObjectIds": [str(cup.id), str(book.id)],
                             "chosenObjectId": str(book.id)}}
    assert photo_reasons(a0, [cup, book], [], scene_attributes, mission_choices=picked) == []
    context = _context(["M05:A0:1"], ["M05:A0:1"])
    check = photo_eligibility(a0, [cup, book], (), (), {"preference": {}}, context)
    assert check.missing == ("choices",)
