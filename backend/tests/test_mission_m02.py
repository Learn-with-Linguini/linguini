"""Multiple-mission planning, per-mission photo eligibility and the M02 A1 lesson."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.features.learning_tasks.mission_m02 import (
    M02LessonResult,
    fallback_m02_lesson,
    validate_m02_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import photo_eligibility, plan_missions
from app.services.mission_lessons_m02 import m02_payload

M01 = get_mission("M01", "A1", 1)
M02 = get_mission("M02", "A1", 2)
CUP, BOOK, TABLE = uuid4(), uuid4(), uuid4()


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None)


def rel(subject, relation, reference):
    return SimpleNamespace(
        id=uuid4(), subject_scene_object_id=subject, relation=relation,
        reference_scene_object_id=reference,
    )


COLOURED = [obj(CUP, "cup", color="red"), obj(BOOK, "book")]
PLAIN = [obj(CUP, "cup"), obj(BOOK, "book")]
ON = [rel(CUP, "on", BOOK)]


@pytest.mark.parametrize(("objects", "relations", "m01", "m02"), [
    (COLOURED, [], True, False),
    (PLAIN, ON, False, True),
    (COLOURED, ON, True, True),
    (PLAIN, [], False, False),
    (PLAIN, [rel(CUP, "inside", BOOK)], False, False),
    (PLAIN, [rel(CUP, "nextTo", BOOK)], False, True),
    (PLAIN, [rel(CUP, "inFrontOf", BOOK)], False, True),
    ([obj(CUP, "cup"), obj(BOOK, "Cup ")], ON, False, False),
])
def test_each_mission_checks_only_the_facts_it_needs(objects, relations, m01, m02):
    assert photo_eligibility(M01, objects, relations).eligible is m01
    assert photo_eligibility(M02, objects, relations).eligible is m02


def test_missing_relations_are_named_for_m02_only():
    assert photo_eligibility(M02, PLAIN, []).reasons == (
        "Confirm where one object is on, under, next to, in front of or behind another.",
    )
    assert photo_eligibility(M01, PLAIN, []).reasons == (
        "Confirm the colour of at least one object.",
    )


@pytest.mark.parametrize(("objects", "relations", "planned"), [
    (COLOURED, [], ["M01"]),
    (PLAIN, ON, ["M02"]),
    (COLOURED, ON, ["M01", "M02"]),
    (PLAIN, [], []),
])
def test_every_mission_the_photo_fits_is_planned(objects, relations, planned):
    plan = plan_missions([M01, M02], objects, relations)
    assert [mission.mission_id for mission in plan] == planned


def _payload(language="fr", relations=None, progress=None):
    objects = [obj(CUP, "cup"), obj(BOOK, "book"), obj(TABLE, "table")]
    words = [
        SimpleNamespace(display_text="tasse", gender="feminine"),
        SimpleNamespace(display_text="livre", gender="masculine"),
        SimpleNamespace(display_text="table", gender="feminine"),
    ] if language == "fr" else [
        SimpleNamespace(display_text="taza", gender="feminine"),
        SimpleNamespace(display_text="libro", gender="masculine"),
        SimpleNamespace(display_text="mesa", gender="feminine"),
    ]
    articles = {"fr": ("la", "le", "la"), "es": ("la", "el", "la")}[language]
    scene = SimpleNamespace(objects=[
        SimpleNamespace(key=str(key), article=article, gender=gender)
        for key, article, gender in zip(
            (CUP, BOOK, TABLE), articles, ("feminine", "masculine", "feminine"), strict=True,
        )
    ])
    relations = relations if relations is not None else [rel(CUP, "next_to", BOOK)]
    return m02_payload(M02, language, objects, relations, words, scene, progress)


def _relation(payload, index):
    keys = {row["key"]: row for row in payload["relations"]}
    return keys[payload["selected"][index]]


def test_review_relation_keys_get_their_reviewed_answer():
    (relation,) = _payload(relations=[rel(CUP, "inFrontOf", BOOK)])["relations"]
    assert relation["statement"] == "La tasse est devant le livre."
    assert relation["answer"] == "Elle est devant le livre."


def test_statement_groups_the_contracted_position_into_one_tile():
    (relation,) = _payload()["relations"]
    assert relation["statementTiles"] == ["La", "tasse", "est", "à côté du", "livre", "."]
    assert relation["statement"] == "La tasse est à côté du livre."
    (spanish,) = _payload("es")["relations"]
    assert spanish["statement"] == "La taza está al lado del libro."
    assert spanish["answer"] == "Está al lado del libro."
    assert spanish["whereQuestion"] == "¿Dónde está la taza?"


def test_one_relation_is_reused_for_both_tasks():
    payload = _payload()
    assert payload["selected"][0] == payload["selected"][1]


def test_task_two_prefers_another_pair_and_unfamiliar_phrases_come_first():
    relations = [rel(CUP, "on", TABLE), rel(BOOK, "under", TABLE)]
    unseen = _payload("es", relations)
    assert [_relation(unseen, i)["position"] for i in (0, 1)] == ["on", "under"]
    familiar = _payload("es", relations, {"terms": {"sobre": 0.9}})
    assert [_relation(familiar, i)["position"] for i in (0, 1)] == ["under", "on"]


def test_fallback_builds_four_parts_in_order_from_confirmed_facts():
    relations = [rel(CUP, "on", TABLE), rel(BOOK, "under", TABLE)]
    payload = _payload("es", relations)
    result = fallback_m02_lesson(payload)
    assert [q.purpose for q in result.questions] == [
        "choosePosition", "describeLocation", "askWhere", "understandAnswer",
    ]
    choose, describe, ask, understand = result.questions
    assert choose.prompt == "Where is the cup in relation to the table?"
    labels = {o.option_id: o.label for o in choose.options}
    assert labels[choose.correct_option_id] == "sobre"
    assert set(labels.values()) == {"sobre", "debajo de", "al lado de"}
    assert describe.correct_text == "La taza está sobre la mesa."
    assert sorted(describe.token_bank) == sorted(
        ["La", "taza", "está", "sobre", "la", "mesa", ".", "debajo de"]
    )
    assert ask.correct_text == "¿Dónde está el libro?"
    assert ask.prompt == "Ask where the book is."
    assert "Está debajo de la mesa." in understand.prompt
    assert understand.correct_option_id == "under"
    assert {o.option_id for o in understand.options} == {"under", "on", "next_to"}


def test_inverse_relations_are_not_offered_as_wrong_phrases():
    payload = _payload("es", [rel(CUP, "next_to", BOOK), rel(BOOK, "under", CUP)])
    choose = fallback_m02_lesson(payload).questions[0]
    assert {o.label for o in choose.options} == {"al lado de", "debajo de", "delante de"}


@pytest.mark.parametrize("change", [
    lambda data: data["questions"][0].update(correct_option_id="phrase-9"),
    lambda data: data["questions"][3].update(correct_option_id="next_to"),
    lambda data: data["questions"][3].update(prompt="Which picture?"),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"][1].update(token_bank=["La", "tasse"]),
    lambda data: data["questions"][2].update(correct_text="Où est le livre ?"),
    lambda data: data["questions"][1].update(relation_key="other"),
    lambda data: data["questions"].pop(2),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    payload = _payload()
    data = fallback_m02_lesson(payload).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m02_lesson(payload, M02LessonResult.model_validate(data))
