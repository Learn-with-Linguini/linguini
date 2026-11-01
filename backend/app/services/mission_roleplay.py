"""Stable fictional roleplay assignments for ownership and preference missions."""

import random

from app.schemas.roleplay import OwnershipFact, PreferenceFact


def _marked_objects(objects, markers):
    """Confirmed objects with a review marker, one per label, in marker order."""
    candidates = []
    labels = set()
    for obj in objects:
        label = obj.label.strip()
        folded = label.casefold()
        marker = markers.get(str(obj.id), markers.get(obj.id))
        if not label or folded in labels or not isinstance(marker, int) or marker < 1:
            continue
        labels.add(folded)
        candidates.append((marker, obj))
    candidates.sort(key=lambda item: (item[0], str(item[1].id)))
    return [obj for _marker, obj in candidates]


def assign_roleplay(mission, session_id, objects, markers):
    """Assign three distinct confirmed objects without making learner claims."""
    if (
        str(mission.practice_level) != "A1"
        or mission.mission_id not in {"M04", "M05"}
    ):
        return []
    candidates = _marked_objects(objects, markers)
    if len(candidates) < 3:
        return []
    rng = random.Random(f"{session_id}:{mission.mission_id}:roleplay")
    rng.shuffle(candidates)
    selected = candidates[:3]
    facts = []
    for index, obj in enumerate(selected):
        if mission.mission_id == "M04":
            fact = OwnershipFact(
                scene_object_id=obj.id,
                owner_type="learner" if index == 0 else "namedCharacter",
                owner_names=[] if index == 0 else ["Ana" if index == 1 else "Leo"],
                possessive_person="first" if index == 0 else "third",
                possessive_number="singular",
                source="assignedRoleplay",
                is_fictional=True,
            )
        else:
            fact = PreferenceFact(
                scene_object_id=obj.id,
                subject_type="learner" if index == 0 else "namedCharacter",
                subject_names=[] if index == 0 else ["Ana" if index == 1 else "Leo"],
                subject_person="first" if index == 0 else "third",
                subject_number="singular",
                preference="like" if index != 1 else "dislike",
                source="assignedRoleplay",
                is_fictional=True,
            )
        facts.append(fact.model_dump(mode="json", by_alias=True))
    return facts


def assign_a0_scenario(mission, session_id, objects, markers):
    """The A0 lesson's pretend scenario, in the learner-choice shape it replaces.

    M04: one object is the learner's. M05: of two objects, the learner likes the first,
    or does not like it and picks the second. ``None`` when the photo has too few.
    """
    if str(mission.practice_level) != "A0" or mission.mission_id not in {"M04", "M05"}:
        return None
    candidates = _marked_objects(objects, markers)
    if len(candidates) < 2:
        return None
    rng = random.Random(f"{session_id}:{mission.mission_id}:scenario")
    rng.shuffle(candidates)
    focus, other = candidates[:2]
    if mission.mission_id == "M04":
        return {"ownedObjectId": str(focus.id), "pretend": True}
    return {"preference": {
        "sceneObjectIds": [str(focus.id), str(other.id)],
        "chosenObjectId": str(focus.id),
        "reaction": rng.choice(["like", "dislike"]),
        "pretend": True,
    }}
