"""Explicitly assigned fictional facts used by A1 roleplay missions."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from app.schemas.base import ApiModel

ROLEPLAY_CAST = ("Ana", "Leo")
_SUBJECT_TYPES = Literal[
    "learner", "namedCharacter", "namedCharacterGroup", "learnerAndCharacter"
]


def _validate_subject(subject_type, names, person, number):
    if any(name not in ROLEPLAY_CAST for name in names):
        raise ValueError("roleplay names must be in the assigned cast")
    if len(names) != len(set(names)):
        raise ValueError("roleplay names must be distinct")
    if subject_type == "learner":
        expected = ([], "first", "singular")
        actual = (names, person, number)
        if actual != expected:
            raise ValueError("learner facts use first person singular without names")
    elif subject_type == "namedCharacter":
        if len(names) != 1 or (person, number) != ("third", "singular"):
            raise ValueError("named character facts use one name and third person singular")
    elif subject_type == "namedCharacterGroup":
        if len(names) < 2 or (person, number) != ("third", "plural"):
            raise ValueError("named character groups use multiple names and third person plural")
    elif subject_type == "learnerAndCharacter":
        if len(names) < 1 or (person, number) != ("first", "plural"):
            raise ValueError("learner and character facts use first person plural with a name")


class OwnershipFact(ApiModel):
    fact_type: Literal["ownership"] = "ownership"
    scene_object_id: UUID
    owner_type: _SUBJECT_TYPES
    owner_names: list[str]
    possessive_person: Literal["first", "second", "third"]
    possessive_number: Literal["singular", "plural"]
    source: Literal["assignedRoleplay"]
    is_fictional: Literal[True]

    @model_validator(mode="after")
    def validate_owner(self) -> OwnershipFact:
        _validate_subject(
            self.owner_type, self.owner_names, self.possessive_person, self.possessive_number
        )
        return self


class PreferenceFact(ApiModel):
    fact_type: Literal["preference"] = "preference"
    scene_object_id: UUID
    subject_type: _SUBJECT_TYPES
    subject_names: list[str]
    subject_person: Literal["first", "second", "third"]
    subject_number: Literal["singular", "plural"]
    preference: Literal["like", "dislike"]
    source: Literal["assignedRoleplay"]
    is_fictional: Literal[True]

    @model_validator(mode="after")
    def validate_subject(self) -> PreferenceFact:
        _validate_subject(
            self.subject_type, self.subject_names, self.subject_person, self.subject_number
        )
        return self


RoleplayFact = Annotated[OwnershipFact | PreferenceFact, Field(discriminator="fact_type")]
_ROLEPLAY_FACTS = TypeAdapter(list[RoleplayFact])


def parse_roleplay_facts(raw, object_ids) -> list[OwnershipFact | PreferenceFact] | None:
    """Validate persisted roleplay facts against the scene's confirmed object IDs."""
    if not isinstance(raw, list):
        return None
    try:
        facts = _ROLEPLAY_FACTS.validate_python(raw)
    except (ValidationError, TypeError, ValueError):
        return None
    confirmed = {str(getattr(object_id, "id", object_id)) for object_id in object_ids}
    seen = set()
    for fact in facts:
        object_id = str(fact.scene_object_id)
        if object_id not in confirmed or object_id in seen:
            return None
        seen.add(object_id)
    return facts
