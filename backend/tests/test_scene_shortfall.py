"""A scene too thin for any mission is reported, never turned into an unchecked lesson."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.learning_errors import register_learning_errors
from app.missions import get_mission
from app.repositories.practice import InsufficientSceneError
from app.schemas.enums import SessionMode
from app.schemas.sessions import SceneShortfall as SceneShortfallSchema
from app.services.mission_eligibility import (
    SHORTFALL_KINDS,
    lesson_missions,
    photo_eligibility,
    scene_shortfall,
)
from app.services.shortfall_steps import mission_steps

A1 = [get_mission(mission_id, "A1", 1) for mission_id in ("M01", "M03")] + [
    get_mission("M02", "A1", 2)
]
CUP, BOOK = uuid4(), uuid4()


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None,
                           bounding_box={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})


def counted(quantity, label="book"):
    return {"sceneObjectIds": [str(BOOK)], "label": label, "quantity": quantity,
            "suggestedQuantity": None, "source": "entered"}


ON = [SimpleNamespace(
    id=uuid4(), subject_scene_object_id=CUP, relation="on", reference_scene_object_id=BOOK,
)]


def test_a_scene_that_fits_a_mission_has_no_shortfall():
    full = [obj(CUP, "cup", color="red"), obj(BOOK, "book", color="blue")]
    assert scene_shortfall(A1, full, ON) is None
    # A count alone is enough for M03.
    assert scene_shortfall(A1, [obj(BOOK, "book")], [], [counted(3)]) is None


def test_profiles_without_missions_are_never_short():
    b1 = lesson_missions(SessionMode.LESSON, {
        "proficiency_level": "B1", "target_language_code": "es",
    })
    assert b1 == []
    assert scene_shortfall(b1, [obj(BOOK, "book")]) is None


def test_each_check_names_the_kind_of_fact_it_lacks():
    m01, m03, m02 = A1
    one = [obj(BOOK, "book")]
    assert photo_eligibility(m01, one).missing == ("objects", "attributes")
    assert photo_eligibility(m02, one).missing == ("objects", "relations")
    assert photo_eligibility(m03, one, [], [counted(1)]).missing == ("counts",)
    assert photo_eligibility(m03, one, [], [counted(3)]).missing == ()


def test_the_shortfall_asks_for_what_the_closest_missions_need():
    two = [obj(CUP, "cup"), obj(BOOK, "book")]
    shortfall = scene_shortfall(A1, two, [], [counted(1)])
    # M01, M02 and M03 each need one more kind of fact.
    assert shortfall.missing == ("counts", "attributes", "relations")
    by_id = {item["missionId"]: item for item in shortfall.missions}
    assert by_id["M01"]["missing"] == ["attributes"]
    assert by_id["M02"]["missing"] == ["relations"]
    assert by_id["M03"]["reasons"] == ["Count a group of 2 to 10 matching objects."]

    # One object: only M03 is one kind away, so a count is what is asked for.
    shortfall = scene_shortfall(A1, [obj(BOOK, "book")], [], [counted(1)])
    assert shortfall.missing == ("counts",)
    assert [item["missionId"] for item in shortfall.missions][0] == "M03"
    # The stored shape is the session detail's contract.
    SceneShortfallSchema.model_validate(shortfall.as_json())


def test_a2_rules_and_a0_choices_map_to_review_actions():
    compare = get_mission("M03", "A2", 1)
    assert "counts" in photo_eligibility(compare, [obj(BOOK, "book")]).missing
    describe = get_mission("M01", "A2", 1)
    assert photo_eligibility(describe, [obj(BOOK, "book")]).missing[-1] == "objects"
    ownership = get_mission("M04", "A0", 1)
    reviewed = [obj(CUP, "cup"), obj(BOOK, "book")]
    check = photo_eligibility(ownership, reviewed, mission_choices={})
    assert check.missing == ("choices",)
    # A missing learner choice is not something the photo can add.
    a0 = lesson_missions(SessionMode.LESSON, {
        "proficiency_level": "A0", "target_language_code": "es",
    })
    shortfall = scene_shortfall(a0, [obj(BOOK, "book")], mission_choices={})
    assert shortfall is not None
    assert set(shortfall.missing) <= set(SHORTFALL_KINDS)
    assert all(item["missionId"] not in {"M04", "M05"} or item["missing"]
               for item in shortfall.missions)


def test_the_rejection_is_a_structured_422():
    app = FastAPI()
    register_learning_errors(app)
    shortfall = scene_shortfall(A1, [obj(BOOK, "book")], [], [counted(1)])

    @app.put("/review")
    def review():
        raise InsufficientSceneError(shortfall)

    response = TestClient(app).put("/review")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "insufficient_scene"
    assert detail["missing"] == ["counts"]
    assert detail["missions"][0]["missionId"] == "M03"
    assert "try another photo" in detail["message"]


def _counts(objects, *pairs):
    return [
        {"label": label, "quantity": quantity,
         "sceneObjectIds": [str(item.id) for item in objects if item.label == label]}
        for label, quantity in pairs
    ]


def test_steps_say_exactly_what_to_mark_from_the_review():
    m01, m03, m02 = A1
    cup = [obj(CUP, "cup")]
    assert mission_steps(m03, cup, [], _counts(cup, ("cup", 1)), ["counts"]) == [
        {"kind": "counts", "text": "Mark 1 more cup so there are 2 cups."},
    ]
    two = [obj(CUP, "cup"), obj(BOOK, "book", color="blue")]
    assert mission_steps(m01, two, [], [], ["attributes"]) == [{
        "kind": "attributes",
        "text": "Give the cup a colour, size, shape, material, pattern or state you can see.",
    }]
    assert mission_steps(m02, two, [], [], ["relations"]) == [{
        "kind": "relations",
        "text": "Add a connection between two objects, such as “cup on book”.",
    }]
    m04 = get_mission("M04", "A1", 1)
    assert mission_steps(m04, two, [], [], ["objects"]) == [{
        "kind": "objects",
        "text": "Mark 1 more different object you can see (so far: cup and book).",
    }]


def test_a0_steps_ask_for_any_object_and_trim_a_group_that_is_too_big():
    m03 = get_mission("M03", "A0", 1)
    books = [obj(uuid4(), "book") for _ in range(4)]
    assert mission_steps(m03, books, [], _counts(books, ("book", 4)), ["counts"]) == [
        {"kind": "counts", "text": "Remove 1 book marker so there are 3 books."},
    ]
    sofas = [obj(uuid4(), "sofa") for _ in range(4)]
    assert mission_steps(m03, sofas, [], _counts(sofas, ("sofa", 4)), ["counts"]) == [
        {"kind": "counts", "text": "Remove 1 sofa marker so there are 3 sofas."},
    ]
    m01 = get_mission("M01", "A0", 1)
    [step] = mission_steps(m01, [obj(BOOK, "sofa")], [], [], ["objects"])
    assert step["text"] == (
        "Mark 1 more different object you can see (so far: sofa), "
        "such as a cup, a book or a chair."
    )
    assert "not taught" not in step["text"]


def test_a2_comparison_asks_for_a_different_number():
    compare = get_mission("M03", "A2", 1)
    scene = [obj(uuid4(), "cup"), obj(uuid4(), "cup"), obj(uuid4(), "book"), obj(uuid4(), "book")]
    [step] = mission_steps(compare, scene, [], _counts(scene, ("cup", 2), ("book", 2)), ["counts"])
    assert step["text"] == (
        "Mark 1 more cup so there are 3 cups; the two groups need different numbers."
    )
    lone = [obj(uuid4(), "cup"), obj(uuid4(), "cup"), obj(BOOK, "book")]
    [step] = mission_steps(compare, lone, [], _counts(lone, ("cup", 2), ("book", 1)), ["counts"])
    assert step["text"] == "Mark 2 more books so there are 3 books next to the 2 cups."


def test_the_shortfall_carries_steps_for_the_closest_missions():
    shortfall = scene_shortfall(A1, [obj(BOOK, "book")], [], [counted(1)])
    m03 = next(item for item in shortfall.missions if item["missionId"] == "M03")
    assert m03["steps"] == [
        {"kind": "counts", "text": "Mark 1 more book so there are 2 books."},
    ]
    SceneShortfallSchema.model_validate(shortfall.as_json())
