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


def test_provisional_focus_shows_five_reliable_objects_when_available():
    labels = ("cup", "book", "table", "chair", "lamp", "door")
    objects = [obj(uuid4(), label) for label in labels]

    _plan, selected = provisional_mission_focus([M01, M02, M03], objects, [])

    assert selected == [item.id for item in objects[:5]]


def test_provisional_focus_counts_unique_labels_and_retains_repeated_markers():
    labels = ("bench", "bench", "bench", "chair", "chair", "lamp", "tree", "bin", "car")
    objects = [obj(uuid4(), label) for label in labels]
    _plan, selected = provisional_mission_focus([], objects, [])
    kept = [item for item in objects if item.id in selected]
    assert {item.label for item in kept} == {"bench", "chair", "lamp", "tree", "bin"}
    assert selected == [item.id for item in objects[:-1]]


def test_fewer_than_five_unique_labels_keep_all_available_instances():
    objects = [obj(uuid4(), label) for label in ("bench", "bench", "bench", "chair", "chair")]
    _plan, selected = provisional_mission_focus([], objects, [])
    assert selected == [item.id for item in objects]


def test_unique_selection_ignores_label_case_and_surrounding_whitespace():
    labels = ("bench", " Bench ", "BENCH", "chair", "lamp", "tree", "bin", "car")
    objects = [obj(uuid4(), label) for label in labels]
    _plan, selected = provisional_mission_focus([], objects, [])
    assert selected == [item.id for item in objects[:-1]]


def test_revisit_suggests_words_not_yet_practised_on_the_photo_first():
    labels = ("cup", "book", "table", "chair", "lamp", "door", "rug")
    objects = [obj(uuid4(), label) for label in labels]
    _plan, selected = provisional_mission_focus(
        [], objects, [], practised_labels={" Cup ", "BOOK"},
    )
    # New words fill the five slots; the result keeps the photo's marker order.
    assert selected == [item.id for item in objects[2:]]


def test_revisit_falls_back_to_practised_words_when_the_photo_has_too_few_new_ones():
    objects = [obj(uuid4(), label) for label in ("cup", "book", "table")]
    _plan, selected = provisional_mission_focus([], objects, [], practised_labels={"cup"})
    assert selected == [item.id for item in objects]


def test_revisit_mission_facts_prefer_unpractised_objects():
    labels = ("cup", "book", "plate", "table", "lamp", "door", "rug")
    objects = [obj(uuid4(), label, color="green") for label in labels]
    relations = [
        SimpleNamespace(id=uuid4(), subject_scene_object_id=objects[0].id, relation="on",
                        reference_scene_object_id=objects[1].id),
        SimpleNamespace(id=uuid4(), subject_scene_object_id=objects[2].id, relation="on",
                        reference_scene_object_id=objects[3].id),
    ]
    plan, selected = provisional_mission_focus(
        [M01, M02, M03], objects, relations, practised_labels={"cup", "book"},
    )
    assert "M02" in {mission.mission_id for mission in plan}
    assert {item.label for item in objects if item.id in selected} == {
        "plate", "table", "lamp", "door", "rug",
    }


def test_tasks_plan_from_five_unique_names_with_counting_instances_and_relations():
    objects = [obj(uuid4(), label, color="green", **({"quantity": "3"} if label == "bench" else {}))
               for label in ("bench", "bench", "bench", "chair", "lamp", "tree", "bin", "car")]
    relation = SimpleNamespace(
        id=uuid4(), subject_scene_object_id=objects[0].id,
        relation="on", reference_scene_object_id=objects[3].id,
    )
    candidates = [M01, M02, M03]
    _provisional, selected = provisional_mission_focus(candidates, objects, [relation])
    confirmed = [item for item in objects if item.id in selected]
    assert {item.label for item in confirmed} == {"bench", "chair", "lamp", "tree", "bin"}
    assert objects[-1].id not in selected
    counts = suggested_counted_groups(confirmed)
    bench = next(group for group in counts if group["label"] == "bench")
    assert bench["quantity"] == 3
    assert len(bench["sceneObjectIds"]) == 3
    plan = plan_missions(candidates, confirmed, [relation], counts)
    assert {mission.mission_id for mission in plan} == {"M01", "M02", "M03"}


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




































