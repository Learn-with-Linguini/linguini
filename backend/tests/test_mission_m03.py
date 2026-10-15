"""M03 A1 counted-group eligibility, three-mission planning, quantities and the lesson."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.features.learning_tasks.mission_m03 import (
    M03LessonResult,
    fallback_m03_lesson,
    validate_m03_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.schemas.sessions import ReviewPracticeRequest
from app.services.mission_eligibility import photo_eligibility, plan_missions
from app.services.mission_lessons_m03 import m03_lesson_task, m03_payload
from app.services.quantities import regular_plural, suggested_quantity, wrong_quantities

M01, M02, M03 = (get_mission(mission_id, "A1", 1) for mission_id in ("M01", "M02", "M03"))
CUP, BOOK = uuid4(), uuid4()


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None)


def counted(quantity, ids=(BOOK,), label="book"):
    return {"sceneObjectIds": [str(item) for item in ids], "label": label,
            "quantity": quantity, "suggestedQuantity": None, "source": "entered"}


ON = [SimpleNamespace(
    id=uuid4(), subject_scene_object_id=CUP, relation="on", reference_scene_object_id=BOOK,
)]
FULL = [obj(CUP, "cup", color="red"), obj(BOOK, "book")]


@pytest.mark.parametrize(("groups", "eligible"), [
    ([], False), ([counted(1)], False), ([counted(2)], True), ([counted(10)], True),
])
def test_m03_needs_a_counted_group_of_two_to_ten(groups, eligible):
    result = photo_eligibility(M03, [obj(BOOK, "book")], [], groups)
    assert result.eligible is eligible
    if not eligible:
        assert result.reasons == ("Count a group of 2 to 10 matching objects.",)


def test_a_count_alone_never_satisfies_m01_or_m02():
    objects, groups = [obj(BOOK, "book")], [counted(3)]
    assert not photo_eligibility(M01, objects, [], groups).eligible
    assert not photo_eligibility(M02, objects, [], groups).eligible


@pytest.mark.parametrize(("objects", "relations", "groups", "passed", "planned"), [
    ([obj(BOOK, "book")], [], [counted(3)], set(), ["M03"]),
    (FULL, ON, [counted(3)], set(), ["M01"]),
    (FULL, ON, [counted(3)], {"M01"}, ["M01", "M02"]),
    (FULL, ON, [counted(3)], {"M01", "M02"}, ["M01", "M02", "M03"]),
    (FULL, ON, [counted(3)], {"M03"}, ["M01", "M03"]),
    (FULL, ON, [counted(1)], {"M01", "M02"}, ["M01", "M02"]),
    (FULL, [], [counted(3)], {"M01"}, ["M01", "M03"]),
])
def test_three_missions_join_with_at_most_one_new_pattern(
    objects, relations, groups, passed, planned,
):
    plan = plan_missions([M01, M02, M03], objects, relations, passed, groups)
    assert [mission.mission_id for mission in plan] == planned


@pytest.mark.parametrize(("value", "expected"), [
    ("3", 3), ("three", 3), (" Two books", 2), ("10", 10), ("11", None), ("0", None),
    ("several", None), ("", None), (None, None), (3, None),
])
def test_only_a_one_to_ten_quantity_is_suggested(value, expected):
    assert suggested_quantity(value) == expected


@pytest.mark.parametrize(("language", "noun", "plural"), [
    ("es", "libro", "libros"), ("es", "taza", "tazas"), ("es", "flor", "flores"),
    ("es", "pared", "paredes"), ("es", "lápiz", None), ("es", "examen", None),
    ("es", "camión", None), ("es", "papel higiénico", None),
    ("fr", "livre", "livres"), ("fr", "tasse", "tasses"), ("fr", "cheval", None),
    ("fr", "bateau", None), ("fr", "bijou", None), ("fr", "nez", None), ("de", "Buch", None),
])
def test_only_reviewed_regular_plurals_are_produced(language, noun, plural):
    assert regular_plural(language, noun) == plural


def test_wrong_quantities_are_nearby_and_within_range():
    assert wrong_quantities(3, 2, 10) == [4, 2, 5]
    assert wrong_quantities(10, 2, 10) == [9, 8, 7]
    assert wrong_quantities(2, 2, 10) == [3, 4, 5]


@pytest.mark.parametrize("quantity", [0, 11])
def test_review_rejects_out_of_range_counts(quantity):
    with pytest.raises(ValidationError):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={BOOK: quantity})


def test_review_rejects_counts_for_unselected_objects():
    with pytest.raises(ValidationError, match="Counts must reference selected objects"):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={CUP: 3})


def _payload(language="es", quantity=3, display="libro", plural_form=None, groups=None):
    words = [SimpleNamespace(display_text=display, plural_form=plural_form)]
    return m03_payload(
        M03, language, [obj(BOOK, "book")], [], words, None,
        [counted(quantity)] if groups is None else groups,
    )


@pytest.mark.parametrize(("language", "display", "statement"), [
    ("es", "libro", "Hay tres libros."), ("fr", "livre", "Il y a trois livres."),
])
def test_fallback_teaches_and_builds_the_confirmed_quantity(language, display, statement):
    payload = _payload(language, display=display)
    result = fallback_m03_lesson(payload)
    validate_m03_lesson(payload, result)
    assert statement in result.explanation
    assert [q.purpose for q in result.questions] == [
        "understandQuantity", "chooseQuantity", "buildQuantity",
    ]
    build = result.questions[-1]
    assert build.correct_text == statement
    assert payload["group"]["singular"] in build.token_bank


@pytest.mark.parametrize("quantity", range(2, 11))
def test_every_quantity_in_range_validates(quantity):
    for language, display in (("es", "libro"), ("fr", "livre")):
        payload = _payload(language, quantity, display)
        validate_m03_lesson(payload, fallback_m03_lesson(payload))


@pytest.mark.parametrize("payload", [
    lambda: _payload(display="lápiz"),
    lambda: _payload(plural_form="libritos"),
    lambda: _payload(groups=[]),
    lambda: _payload(groups=[counted(1)]),
    lambda: _payload(groups=[counted(3, ids=(uuid4(),))]),
])
def test_unreviewed_plurals_and_unconfirmed_groups_have_no_lesson(payload):
    payload = payload()
    assert payload["group"] is None
    with pytest.raises(LearningTaskGenerationError):
        fallback_m03_lesson(payload)


def _wrong_statement(data):
    data["questions"][2]["correct_text"] = "Hay cuatro libros."
    data["questions"][2]["token_bank"] = ["Hay", "cuatro", "libros", ".", "libro", "tres"]


@pytest.mark.parametrize("change", [
    _wrong_statement,
    lambda data: data["questions"][1].update(object_key=str(uuid4())),
    lambda data: data["questions"][2].update(token_bank=["Hay", "tres", "libros", "."]),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"].pop(2),
    lambda data: data.update(explanation="Count things."),
])
def test_validator_rejects_wrong_counts_references_and_plurals(change):
    payload = _payload()
    data = fallback_m03_lesson(payload).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m03_lesson(payload, M03LessonResult.model_validate(data))


def test_corrections_separate_quantity_from_plural_mistakes():
    payload = _payload()
    result = fallback_m03_lesson(payload)
    task = m03_lesson_task(uuid4(), M03, payload, result, {str(BOOK): uuid4()})
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
    choose, build = result.questions[1], result.questions[2]
    by_answer = {
        option.label: [
            rule.mistake for rule in evaluations[choose.question_id].corrections
            if option.option_id in rule.answers
        ]
        for option in choose.options if option.option_id != choose.correct_option_id
    }
    assert by_answer["Hay tres libro."] == ["pluralForm"]
    assert all(mistakes == ["wrongQuantity"] for label, mistakes in by_answer.items()
               if label != "Hay tres libro.")
    rules = {rule.mistake: rule.answers for rule in evaluations[build.question_id].corrections}
    assert "Hay tres libro." in rules["pluralForm"]
    assert "Hay cuatro libros." in rules["wrongQuantity"]
    assert rules["wordOrder"] == []
    assert [item.evidence_type for item in task.answer_key.question_evaluations] == [
        "recognition", "recognition", "construction",
    ]
    assert evaluations[result.questions[0].question_id].vocabulary_item_ids == []
