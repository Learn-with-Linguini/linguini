"""Multiple-mission planning, per-mission photo eligibility and the M02 A1 lesson."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.missions import definition_file_name, get_mission
from app.services.mission_eligibility import photo_eligibility, plan_missions

DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least 2 different objects."
)
ONE_DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least one object."
)
M01 = get_mission("M01", "A1", 1)
M02 = get_mission("M02", "A1", 2)
CUP = UUID("33333333-0000-0000-0000-000000000000")
BOOK = UUID("11111111-0000-0000-0000-000000000000")
TABLE = UUID("22222222-0000-0000-0000-000000000000")
SESSION = UUID("44444444-4444-4444-4444-444444444444")


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None)


def rel(subject, relation, reference):
    return SimpleNamespace(
        id=uuid4(), subject_scene_object_id=subject, relation=relation,
        reference_scene_object_id=reference,
    )


COLOURED = [obj(CUP, "cup", color="red"), obj(BOOK, "book", color="blue")]
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
        DETAIL_REASON,
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




def _relation(payload):
    keys = {row["key"]: row for row in payload["relations"]}
    return keys[payload["selected"][0]]


def _labels(question):
    return {option.option_id: option.label for option in question.options}


def test_saved_version_one_lessons_still_resolve_their_definition():
    old = get_mission("M02", "A1", 1)
    assert old is not None and old.expected_performance.min_assessed_questions == 3
    assert M02.expected_performance.min_assessed_questions == 4
    assert definition_file_name(old) == "M02-A1.toml"
    assert definition_file_name(M02) == "M02-A1-2.toml"


























def _mutate(result, index, **changes):
    questions = list(result.questions)
    questions[index] = questions[index].model_copy(update=changes)
    return result.model_copy(update={"questions": questions})






def test_review_numbers_follow_detection_then_added_order():
    from app.repositories.postgres.workflow import review_marker_numbers
    detected = [{"id": str(TABLE)}, {"id": str(BOOK)}, {"id": str(CUP)}]
    added = [uuid4(), uuid4()]
    assert review_marker_numbers(detected, [TABLE, CUP], added) == {
        str(TABLE): 1, str(CUP): 3, str(added[0]): 4, str(added[1]): 5,
    }


def test_review_numbers_follow_the_visible_suggestion_subset():
    from app.repositories.postgres.workflow import review_marker_numbers
    detected = [{"id": str(TABLE)}, {"id": str(BOOK)}, {"id": str(CUP)}]
    added = [uuid4()]

    assert review_marker_numbers(
        detected, [BOOK, CUP], added, suggested_ids=[BOOK, CUP]
    ) == {str(BOOK): 1, str(CUP): 2, str(added[0]): 3}
