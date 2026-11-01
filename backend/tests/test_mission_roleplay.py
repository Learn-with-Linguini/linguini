"""Validated fictional assignments and reviewed language forms for A1 missions."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.roleplay import OwnershipFact, PreferenceFact, parse_roleplay_facts
from app.services.mission_roleplay import assign_roleplay


def _ownership(object_id, **changes):
    return {
        "factType": "ownership",
        "sceneObjectId": str(object_id),
        "ownerType": "learner",
        "ownerNames": [],
        "possessivePerson": "first",
        "possessiveNumber": "singular",
        "source": "assignedRoleplay",
        "isFictional": True,
        **changes,
    }


def _preference(object_id, **changes):
    return {
        "factType": "preference",
        "sceneObjectId": str(object_id),
        "subjectType": "learner",
        "subjectNames": [],
        "subjectPerson": "first",
        "subjectNumber": "singular",
        "preference": "like",
        "source": "assignedRoleplay",
        "isFictional": True,
        **changes,
    }


@pytest.mark.parametrize("changes", [
    {"source": "inferred"},
    {"isFictional": False},
    {"ownerType": "learner", "ownerNames": ["Ana"]},
    {"ownerType": "namedCharacter", "ownerNames": ["Rin"],
     "possessivePerson": "third"},
])
def test_roleplay_facts_reject_unsupported_assignments(changes):
    with pytest.raises(ValidationError):
        OwnershipFact.model_validate(_ownership(uuid4(), **changes))


def test_roleplay_parser_fails_safe_for_unconfirmed_and_repeated_objects():
    first, second = uuid4(), uuid4()
    assert parse_roleplay_facts([_ownership(first)], [second]) is None
    assert parse_roleplay_facts([_ownership(first), _preference(first)], [first]) is None
    assert parse_roleplay_facts([_ownership(first, source="inferred")], [first]) is None
    assert parse_roleplay_facts(
        [_ownership(first, ownerType="namedCharacter", ownerNames=["Ana"],
                    possessivePerson="third")], [first]
    ) is not None


def test_preference_fact_requires_an_explicit_preference_and_subject():
    object_id = uuid4()
    with pytest.raises(ValidationError):
        PreferenceFact.model_validate(_preference(object_id, preference="maybe"))
    with pytest.raises(ValidationError):
        PreferenceFact.model_validate(
            _preference(object_id, subjectType="learner", subjectNames=["Ana"])
        )


def test_assignments_are_deterministic_confirmed_distinct_and_bounded():
    objects = [
        SimpleNamespace(id=uuid4(), label="Book"),
        SimpleNamespace(id=uuid4(), label="book"),
        SimpleNamespace(id=uuid4(), label="Cup"),
        SimpleNamespace(id=uuid4(), label="Spoon"),
        SimpleNamespace(id=uuid4(), label="Bowl"),
    ]
    markers = {str(obj.id): index + 1 for index, obj in enumerate(objects)}
    mission = SimpleNamespace(mission_id="M04", practice_level="A1")
    assigned = assign_roleplay(mission, "session-a", objects, markers)
    assert assigned == assign_roleplay(mission, "session-a", objects, markers)
    assert len(assigned) == 3
    assert len({fact["sceneObjectId"] for fact in assigned}) == len(assigned)
    assert {fact["sceneObjectId"] for fact in assigned} <= {
        str(obj.id) for obj in objects
    }
    assert len({obj.label.casefold() for obj in objects
                if str(obj.id) in {fact["sceneObjectId"] for fact in assigned}}) == len(assigned)
    assert assigned[0]["ownerType"] == "learner"
    assert assigned[1]["ownerNames"] == ["Ana"]


def test_assignments_require_three_distinct_confirmed_objects():
    objects = [
        SimpleNamespace(id=uuid4(), label="book"),
        SimpleNamespace(id=uuid4(), label="cup"),
    ]
    markers = {str(obj.id): index + 1 for index, obj in enumerate(objects)}
    assert assign_roleplay(
        SimpleNamespace(mission_id="M04", practice_level="A1"),
        "session-a",
        objects,
        markers,
    ) == []


def test_m05_assignments_include_like_and_dislike_facts():
    objects = [SimpleNamespace(id=uuid4(), label=name) for name in ("book", "cup", "spoon")]
    markers = {str(obj.id): index + 1 for index, obj in enumerate(objects)}
    facts = assign_roleplay(
        SimpleNamespace(mission_id="M05", practice_level="A1"),
        "session-b",
        objects,
        markers,
    )
    assert [fact["preference"] for fact in facts] == ["like", "dislike", "like"]
    assert [fact["subjectNames"] for fact in facts] == [[], ["Ana"], ["Leo"]]


def test_non_missions_and_objects_without_review_markers_are_not_assigned():
    objects = [SimpleNamespace(id=uuid4(), label="book")]
    assert assign_roleplay(
        SimpleNamespace(mission_id="M03", practice_level="A1"), "s", objects, {}
    ) == []
    assert assign_roleplay(
        SimpleNamespace(mission_id="M04", practice_level="A1"), "s", objects, {}
    ) == []








