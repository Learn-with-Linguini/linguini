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
M02 = get_mission("M02", "A1", 1)
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


def _payload(language="fr", relation="next_to"):
    objects = [obj(CUP, "cup"), obj(BOOK, "book")]
    words = [
        SimpleNamespace(display_text="tasse", gender="feminine"),
        SimpleNamespace(display_text="livre", gender="masculine"),
    ]
    scene = SimpleNamespace(objects=[
        SimpleNamespace(key=str(CUP), article="la", gender="feminine"),
        SimpleNamespace(key=str(BOOK), article="le", gender="masculine"),
    ])
    return m02_payload(M02, language, objects, [rel(CUP, relation, BOOK)], words, scene)


def test_review_relation_keys_get_their_reviewed_answer():
    (relation,) = _payload(relation="inFrontOf")["relations"]
    assert relation["answer"] == "La tasse est devant le livre."


def test_payload_uses_reviewed_questions_and_contracted_answers():
    payload = _payload()
    assert [row["whereQuestion"] for row in payload["objects"]] == [
        "Où est la tasse ?", "Où est le livre ?",
    ]
    (relation,) = payload["relations"]
    assert relation["answer"] == "La tasse est à côté du livre."
    assert relation["meaning"] == "The cup is next to the book."
    assert payload["languagePattern"]["expression"] == "à côté de"


def test_fallback_builds_and_quotes_a_confirmed_answer_in_spanish():
    words = [
        SimpleNamespace(display_text="taza", gender="feminine"),
        SimpleNamespace(display_text="libro", gender="masculine"),
    ]
    scene = SimpleNamespace(objects=[
        SimpleNamespace(key=str(CUP), article="la", gender="feminine"),
        SimpleNamespace(key=str(BOOK), article="el", gender="masculine"),
    ])
    payload = m02_payload(M02, "es", PLAIN, [rel(CUP, "next_to", BOOK)], words, scene)
    result = fallback_m02_lesson(payload)
    purposes = [question.purpose for question in result.questions]
    assert purposes == ["recogniseQuestion", "buildQuestion", "understandAnswer"]
    build = result.questions[1]
    assert build.correct_text == "¿Dónde está la taza?"
    assert sorted(build.token_bank) == sorted(["¿Dónde", "está", "la", "taza", "?"])
    assert "La taza está al lado del libro." in result.questions[2].prompt


@pytest.mark.parametrize("change", [
    lambda data: data["questions"][2].update(correct_option_id="answer-2"),
    lambda data: data["questions"][2].update(relation_key=None),
    lambda data: data["questions"][2].update(prompt="What does it mean?"),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"][1].update(token_bank=["Où", "est", "la"]),
    lambda data: data["questions"][1].update(correct_text="Où est le livre ?"),
    lambda data: data["questions"].pop(2),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    payload = _payload()
    data = fallback_m02_lesson(payload).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m02_lesson(payload, M02LessonResult.model_validate(data))
