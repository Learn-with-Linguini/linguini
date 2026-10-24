"""M03 A1 counted-group eligibility, three-mission planning, quantities and the lesson."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.missions import get_mission
from app.schemas.sessions import ReviewPracticeRequest
from app.services.mission_eligibility import (
    photo_eligibility,
    plan_missions,
    provisional_mission_focus,
    suggested_counted_groups,
)
from app.services.quantities import suggested_quantity

M01, M02, M03 = (get_mission(mission_id, "A1", 1) for mission_id in ("M01", "M02", "M03"))
CUP, BOOK = uuid4(), uuid4()


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None,
                           bounding_box={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})


def counted(quantity, ids=(BOOK,), label="book", suggested=None):
    return {"sceneObjectIds": [str(item) for item in ids], "label": label,
            "quantity": quantity, "suggestedQuantity": suggested, "source": "entered"}


ON = [SimpleNamespace(
    id=uuid4(), subject_scene_object_id=CUP, relation="on", reference_scene_object_id=BOOK,
)]
FULL = [obj(CUP, "cup", color="red"), obj(BOOK, "book", color="blue")]


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


@pytest.mark.parametrize(("objects", "relations", "groups", "planned"), [
    ([obj(BOOK, "book")], [], [counted(3)], ["M03"]),
    (FULL, ON, [counted(3)], ["M01", "M02", "M03"]),
    (FULL, ON, [counted(1)], ["M01", "M02"]),
    (FULL, [], [counted(3)], ["M01", "M03"]),
])
def test_every_mission_the_photo_fits_is_planned_up_to_three(objects, relations, groups, planned):
    plan = plan_missions([M01, M02, M03], objects, relations, groups)
    assert [mission.mission_id for mission in plan] == planned


def test_provisional_focus_uses_suggested_facts_but_returns_a_small_review_set():
    repeated = [
        obj(uuid4(), "book", quantity="3"),
        obj(uuid4(), "book", quantity="3"),
        obj(uuid4(), "book", quantity="3"),
    ]
    plan, selected = provisional_mission_focus([M01, M02, M03], repeated, [])
    assert [mission.mission_id for mission in plan] == ["M03"]
    assert selected == [item.id for item in repeated]


def test_provisional_count_never_exceeds_visible_instances():
    objects = [
        obj(uuid4(), "book", quantity="3"),
        obj(uuid4(), "cup", quantity="2"),
        obj(uuid4(), "table", quantity="4"),
    ]

    groups = suggested_counted_groups(objects)

    assert [group["quantity"] for group in groups] == [1, 1, 1]
    plan, selected = provisional_mission_focus([M01, M02, M03], objects, [])
    assert "M03" not in {mission.mission_id for mission in plan}
    assert selected == [item.id for item in objects]


@pytest.mark.parametrize(("value", "expected"), [
    ("3", 3), ("three", 3), (" Two books", 2), ("10", 10), ("11", None), ("0", None),
    ("several", None), ("", None), (None, None), (3, None),
])
def test_only_a_one_to_ten_quantity_is_suggested(value, expected):
    assert suggested_quantity(value) == expected










@pytest.mark.parametrize("quantity", [0, 11])
def test_review_rejects_out_of_range_counts(quantity):
    with pytest.raises(ValidationError):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={BOOK: quantity})


def test_review_rejects_counts_for_unselected_objects():
    with pytest.raises(ValidationError, match="Counts must reference selected objects"):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={CUP: 3})


def _scene(*entries):
    return SimpleNamespace(objects=[
        SimpleNamespace(key=str(key), gender=gender) for key, gender in entries
    ])




def _choose(result):
    return result.questions[0]


def _build(result):
    return result.questions[1]


def _match(result):
    return result.questions[2]


def _correct_option(question):
    return next(option for option in question.options
                if option.option_id == question.correct_option_id)




































