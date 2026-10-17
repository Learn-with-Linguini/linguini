"""Validated fictional assignments and reviewed language forms for A1 missions."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.roleplay import OwnershipFact, PreferenceFact, parse_roleplay_facts
from app.services.mission_roleplay import assign_roleplay
from app.services.possessives import ownership_statement, possessive_sentence
from app.services.preferences import preference_sentence


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
    mission = SimpleNamespace(mission_id="M04")
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
        SimpleNamespace(mission_id="M04"), "session-a", objects, markers
    ) == []


def test_m05_assignments_include_like_and_dislike_facts():
    objects = [SimpleNamespace(id=uuid4(), label=name) for name in ("book", "cup", "spoon")]
    markers = {str(obj.id): index + 1 for index, obj in enumerate(objects)}
    facts = assign_roleplay(SimpleNamespace(mission_id="M05"), "session-b", objects, markers)
    assert [fact["preference"] for fact in facts] == ["like", "dislike", "like"]
    assert [fact["subjectNames"] for fact in facts] == [[], ["Ana"], ["Leo"]]


def test_non_missions_and_objects_without_review_markers_are_not_assigned():
    objects = [SimpleNamespace(id=uuid4(), label="book")]
    assert assign_roleplay(SimpleNamespace(mission_id="M03"), "s", objects, {}) == []
    assert assign_roleplay(SimpleNamespace(mission_id="M04"), "s", objects, {}) == []


@pytest.mark.parametrize(("language", "person", "name", "noun", "gender", "expected"), [
    ("es", "first", None, "libro", "el", "Es mi libro."),
    ("es", "third", "Ana", "taza", "la", "Es su taza."),
    ("fr", "first", None, "livre", "masculine", "C'est mon livre."),
    ("fr", "third", "Ana", "tasse", "la", "C'est sa tasse."),
    ("fr", "first", None, "assiette", "feminine", "C'est mon assiette."),
    ("de", "first", None, "Buch", "das", "Das ist mein Buch."),
    ("de", "first", None, "Tasse", "die", "Das ist meine Tasse."),
    ("de", "third", "Leo", "Stuhl", "der", "Das ist sein Stuhl."),
    ("de", "third", "Ana", "Tasse", "feminine", "Das ist ihre Tasse."),
    ("ko", "first", None, "책", "masculine", "제 책이에요."),
    ("ko", "third", "Leo", "사과", "feminine", "레오의 사과예요."),
])
def test_possessive_language_tables(language, person, name, noun, gender, expected):
    assert possessive_sentence(language, person, name, noun, gender) == expected


def test_possessives_refuse_unknown_gender_french_h_and_non_letter_nouns():
    assert possessive_sentence("fr", "first", None, "livre", None) is None
    assert possessive_sentence("fr", "first", None, "haricot", "masculine") is None
    assert possessive_sentence("es", "first", None, "libro!", "masculine") is None


@pytest.mark.parametrize(("language", "owner", "noun", "gender", "expected"), [
    ("es", "Ana", "taza", "la", "Es la taza de Ana."),
    ("fr", "Ana", "tasse", "feminine", "C'est la tasse d'Ana."),
    ("fr", "Leo", "assiette", "la", "C'est l'assiette de Leo."),
    ("de", "Leo", "Buch", "das", "Das ist Leos Buch."),
    ("ko", "Ana", "책", "masculine", "아나의 책이에요."),
])
def test_ownership_statements(language, owner, noun, gender, expected):
    assert ownership_statement(language, owner, noun, gender) == expected


@pytest.mark.parametrize(("language", "person", "name", "like", "noun", "gender", "expected"), [
    ("es", "first", None, True, "libro", "el", "Me gusta el libro."),
    ("es", "third", "Ana", False, "taza", "feminine", "A Ana no le gusta la taza."),
    ("fr", "first", None, False, "tasse", "la", "Je n'aime pas la tasse."),
    ("fr", "first", None, True, "assiette", "feminine", "J'aime l'assiette."),
    ("fr", "third", "Ana", True, "tasse", "feminine", "Ana aime la tasse."),
    ("de", "first", None, True, "Stuhl", "der", "Ich mag den Stuhl."),
    ("de", "first", None, False, "Tasse", "die", "Ich mag die Tasse nicht."),
    ("de", "third", "Leo", False, "Buch", "neuter", "Leo mag das Buch nicht."),
    ("ko", "first", None, True, "책", "masculine", "저는 책을 좋아해요."),
    ("ko", "first", None, False, "사과", "feminine", "저는 사과를 안 좋아해요."),
    ("ko", "third", "Ana", False, "사과", "feminine", "아나는 사과를 안 좋아해요."),
])
def test_preference_language_tables(language, person, name, like, noun, gender, expected):
    assert preference_sentence(language, person, name, like, noun, gender) == expected


def test_preferences_refuse_unknown_gender_french_h_and_unknown_names():
    assert preference_sentence("es", "first", None, True, "libro", None) is None
    assert preference_sentence("fr", "first", None, True, "haricot", "masculine") is None
    assert preference_sentence("de", "third", "Mina", True, "Buch", "das") is None
