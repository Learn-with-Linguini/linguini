"""Stable fictional roleplay assignments for ownership and preference missions."""

import random

from app.schemas.roleplay import OwnershipFact, PreferenceFact


def assign_roleplay(mission, session_id, objects, markers):
    """Assign three distinct confirmed objects without making learner claims."""
    if mission.mission_id not in {"M04", "M05"}:
        return []
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
    if len(candidates) < 3:
        return []
    rng = random.Random(f"{session_id}:{mission.mission_id}:roleplay")
    rng.shuffle(candidates)
    selected = [obj for _marker, obj in candidates[:3]]
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
