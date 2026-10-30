"""Mission planning and per-mission photo eligibility from learner-confirmed scene facts.

Every mission lesson comes from a language pack: the missions offered are the pack's
ready ones, and photo rules are the generic requirements plus each pack mission's own.
"""

import re
from collections import Counter
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode

M01_A0 = ("M01", "A0", 1)
M02_A0 = ("M02", "A0", 1)
M03_A0 = ("M03", "A0", 1)
M04_A0 = ("M04", "A0", 1)
M05_A0 = ("M05", "A0", 1)
M13_A0 = ("M13", "A0", 1)
M01_A1 = ("M01", "A1", 1)
M02_A1 = ("M02", "A1", 2)
M03_A1 = ("M03", "A1", 1)
M04_A1 = ("M04", "A1", 1)
M05_A1 = ("M05", "A1", 1)
M01_A2 = ("M01", "A2", 1)
M02_A2 = ("M02", "A2", 1)
M03_A2 = ("M03", "A2", 1)
M04_A2 = ("M04", "A2", 1)
M06_A2 = ("M06", "A2", 1)
# Implemented variants per stored proficiency level, in catalogue order; a lesson
# assesses at most three. Only the active profile's ``proficiency_level`` selects them.
IMPLEMENTED_MISSIONS = {
    "A0": (M01_A0, M02_A0, M03_A0, M04_A0, M05_A0, M13_A0),
    "A1": (M01_A1, M02_A1, M03_A1, M04_A1, M05_A1),
    "A2": (M01_A2, M02_A2, M03_A2, M04_A2, M06_A2),
}
MAX_LESSON_MISSIONS = {"A0": 3, "A1": 3, "A2": 4}

# Confirmed attribute values clearly different in a photo, the only ones a lesson offers
# as distractors. Values are the scene's English attribute values, not lesson words.
ATTRIBUTE_CONTRASTS = {
    "size": {"big": ("small",), "small": ("big",), "long": ("short",), "short": ("long",)},
    "shape": {"round": ("square", "rectangular"), "square": ("round",),
              "rectangular": ("round",)},
    "material": {"wooden": ("metal", "plastic", "glass"),
                 "metal": ("wooden", "glass", "fabric"),
                 "plastic": ("wooden", "metal", "fabric"),
                 "glass": ("wooden", "metal", "fabric"),
                 "fabric": ("wooden", "metal", "glass"),
                 "stone": ("wooden", "plastic", "fabric")},
    "pattern": {"striped": ("spotted",), "spotted": ("striped",)},
    "state": {"open": ("closed",), "closed": ("open",), "empty": ("full",),
              "full": ("empty",), "clean": ("dirty",), "dirty": ("clean",)},
}


_CONTEXT_UNSET = object()


def lesson_missions(session_mode, profile, language_context=_CONTEXT_UNSET):
    """Missions a new lesson may plan from: the language pack's ready missions that the app
    offers at the profile's level. Empty (no pack, or none ready) keeps the regular lesson.
    """
    if session_mode != SessionMode.LESSON:
        return []
    if language_context is _CONTEXT_UNSET:
        from app.language_packs.context import operation_context

        language_context = operation_context(session_mode, profile)
    if language_context is None:
        return []
    level = str(profile["proficiency_level"] or "").strip().upper()
    offered = {key[0] for key in IMPLEMENTED_MISSIONS.get(level, ())}
    return [
        mission for key in language_context.ready_missions_at(level)
        if key[0] in offered and (mission := get_mission(*key)) is not None
    ]


def lesson_mission(mission):
    """``mission`` at its newest pack template version, keeping saved plans valid.

    A plan saved for an older content version (M02 A1 version 1) is built at the
    version its pack lessons now use.
    """
    from app.language_packs.capabilities import mission_template_key
    from app.language_packs.loader import LanguagePackError

    try:
        key = mission_template_key(mission.mission_id, mission.practice_level)
    except LanguagePackError:
        return mission
    if key[2] == mission.content_version:
        return mission
    return get_mission(*key) or mission


def plan_missions(
    candidates, objects, relations, counted_groups=(), history=(), mission_choices=None,
    language_context=None,
):
    """Select least-planned eligible missions, returning them in catalogue order."""
    if not candidates:
        return []
    eligible = [
        mission for mission in candidates
        if photo_eligibility(
            mission, objects, relations, counted_groups, mission_choices, language_context
        ).eligible
    ]
    counts = Counter(history)
    cap = MAX_LESSON_MISSIONS.get(str(candidates[0].practice_level), 3)
    selected = {
        mission.mission_id
        for _index, mission in sorted(
            enumerate(eligible),
            key=lambda item: (
                not _mission_choice_supplied(item[1], mission_choices),
                counts[item[1].mission_id],
                item[0],
            ),
        )[:cap]
    }
    return [mission for mission in eligible if mission.mission_id in selected]


def suggested_counted_groups(objects):
    """Model-suggested groups used only to focus review, never as lesson evidence."""
    groups = {}
    for obj in objects:
        label = obj.label.strip().casefold()
        raw = (obj.attributes or {}).get("quantity")
        try:
            quantity = int(raw)
        except (TypeError, ValueError):
            continue
        if not 1 <= quantity <= 20:
            continue
        group = groups.setdefault(
            label,
            {"label": obj.label, "quantity": quantity, "sceneObjectIds": []},
        )
        if group["quantity"] == quantity:
            group["sceneObjectIds"].append(str(obj.id))
    # Scene analysis returns one marker per visible instance. Keep provisional
    # planning consistent with the review screen: a model suggestion must not
    # turn one visible marker into a countable group and hide the other objects
    # that could support non-counting missions.
    return [
        {**group, "quantity": min(group["quantity"], len(group["sceneObjectIds"]))}
        for group in groups.values()
    ]


def provisional_mission_focus(candidates, objects, relations, language_context=None):
    """Mission candidates and the smallest suggested fact set worth confirming.

    The return value is presentation guidance over unconfirmed model output. It
    must never be used as the final mission plan or grading evidence.
    """
    counts = suggested_counted_groups(objects)
    plan = plan_missions(candidates, objects, relations, counts, language_context=language_context)
    if candidates and str(candidates[0].practice_level) == "A0":
        planned_keys = {
            (mission.mission_id, str(mission.practice_level), mission.content_version)
            for mission in plan
        }
        for mission in candidates:
            key = (
                mission.mission_id, str(mission.practice_level), mission.content_version,
            )
            if (
                str(mission.practice_level) == "A0"
                and mission.mission_id in {"M04", "M05"}
                and key not in planned_keys
                and photo_eligibility(
                    mission, objects, relations, counts, mission_choices=None,
                ).eligible
            ):
                planned_keys.add(key)
        plan = [
            mission for mission in candidates
            if (
                mission.mission_id, str(mission.practice_level), mission.content_version,
            ) in planned_keys
        ]
    selected = []

    def add(object_id):
        if object_id not in selected:
            selected.append(object_id)

    for mission in plan:
        requirements = mission.photo_requirements
        if requirements.min_coloured_objects:
            seen = set()
            for obj in objects:
                label = obj.label.strip().casefold()
                if label not in seen and scene_attributes(obj):
                    add(obj.id)
                    seen.add(label)
                    if len(seen) >= requirements.min_coloured_objects:
                        break
        if requirements.min_relations:
            for relation in confirmed_relations(mission, objects, relations)[
                : requirements.min_relations
            ]:
                add(relation.subject_scene_object_id)
                add(relation.reference_scene_object_id)
        if requirements.min_counted_groups:
            usable = countable_groups(mission, counts)[: requirements.min_counted_groups]
            for group in usable:
                group_ids = set(group["sceneObjectIds"])
                for obj in objects:
                    if str(obj.id) in group_ids:
                        add(obj.id)
        distinct = {obj.label.strip().casefold() for obj in objects if obj.id in selected}
        for obj in objects:
            if len(distinct) >= requirements.min_confirmed_objects:
                break
            label = obj.label.strip().casefold()
            if label not in distinct:
                add(obj.id)
                distinct.add(label)

    # Fill to five noun labels, not five markers. Keep mission-required facts,
    # then follow analysis usefulness order for additional vocabulary.
    selected_labels = {obj.label.strip().casefold() for obj in objects if obj.id in selected}
    for obj in objects:
        if len(selected_labels) >= 5:
            break
        label = obj.label.strip().casefold()
        if label not in selected_labels:
            selected_labels.add(label)

    # Repeated instances share a vocabulary slot, but retain their own markers,
    # attributes and relations for counting and object-specific lesson questions.
    selected = [obj.id for obj in objects if obj.label.strip().casefold() in selected_labels]
    return plan, selected


def mission_snapshot(mission):
    return {
        "missionId": mission.mission_id,
        "practiceLevel": str(mission.practice_level),
        "contentVersion": mission.content_version,
    }


def snapshot_missions(snapshot):
    """The saved plan's definitions; unknown entries are dropped rather than guessed."""
    return [
        mission for item in snapshot or []
        if (mission := get_mission(
            item["missionId"], item["practiceLevel"], item["contentVersion"]
        )) is not None
    ]




def relation_type(relation):
    """The relation's snake_case type, as review sends camelCase keys such as ``nextTo``."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", "_", relation.relation).lower()


def confirmed_relations(mission, objects, relations):
    """Confirmed relations of an accepted type between two differently named objects."""
    labels = {obj.id: obj.label.strip().casefold() for obj in objects}
    allowed = set(mission.photo_requirements.relations)
    return [
        relation for relation in relations
        if relation_type(relation) in allowed
        and relation.subject_scene_object_id in labels
        and relation.reference_scene_object_id in labels
        and labels[relation.subject_scene_object_id] != labels[relation.reference_scene_object_id]
    ]


# What a learner can add on the review screen, in the order the screen offers it.
SHORTFALL_KINDS = ("objects", "counts", "attributes", "relations")
# Pack missions' own photo rules and the confirmed facts that can satisfy them.
PACK_SHORTFALLS = {
    "M01": ("attributes", "relations"),
    "M02": ("attributes", "relations"),
    "M03": ("counts",),
    "M04": ("attributes", "relations"),
    "M06": ("objects",),
}
# Pack photo reasons that ask for a learner choice rather than more photo facts.
PACK_CHOICE_REASONS = frozenset({
    "Tell Linguini which object is yours.", "Tell Linguini what you would choose.",
})


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()
    # The kinds of confirmed fact that are short: ``SHORTFALL_KINDS`` or ``choices``.
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class SceneShortfall:
    """Why no mission fits the confirmed scene, and what the learner could add."""

    missing: tuple[str, ...]
    missions: tuple[dict, ...]

    def as_json(self):
        return {"missing": list(self.missing), "missions": list(self.missions)}


def scene_shortfall(
    candidates, objects, relations=(), counted_groups=(), mission_choices=None,
    language_context=None,
):
    """``None`` when a mission fits; otherwise what the closest missions still need.

    A profile without implemented missions has nothing to check, so it is never short.
    """
    from app.services.shortfall_steps import mission_steps

    if not candidates or plan_missions(
        candidates, objects, relations, counted_groups, (), mission_choices, language_context,
    ):
        return None
    checks = [
        (mission, photo_eligibility(
            mission, objects, relations, counted_groups, mission_choices, language_context,
        ))
        for mission in candidates
    ]
    # Only facts the review screen can add; a missing learner choice is not the photo's gap.
    actionable = [
        (mission, check, [kind for kind in SHORTFALL_KINDS if kind in check.missing])
        for mission, check in checks
    ]
    actionable = sorted(
        (item for item in actionable if item[2]), key=lambda item: len(item[2])
    )
    closest = len(actionable[0][2]) if actionable else 0
    missing = [
        kind for kind in SHORTFALL_KINDS
        if any(kind in kinds for *_rest, kinds in actionable if len(kinds) == closest)
    ]
    return SceneShortfall(
        missing=tuple(missing or SHORTFALL_KINDS),
        missions=tuple(
            {
                "missionId": mission.mission_id,
                "title": mission.title,
                "missing": kinds,
                "reasons": list(check.reasons),
                "steps": mission_steps(mission, objects, relations, counted_groups, kinds),
            }
            for mission, check, kinds in actionable
        ),
    )


def saved_counted_groups(draft):
    """The learner-confirmed counts saved with the session's review."""
    return list((draft or {}).get("countedGroups") or [])


def countable_groups(mission, counted_groups):
    requirements = mission.photo_requirements
    return [
        group for group in counted_groups
        if requirements.min_quantity <= group["quantity"] <= requirements.max_quantity
    ]








def attribute_contrasts(kind, value):
    return ATTRIBUTE_CONTRASTS.get(kind, {}).get(value.strip().casefold(), ())


def photo_eligibility(
    mission, objects, relations=(), counted_groups=(), mission_choices=None,
    language_context=None,
):
    """Check the confirmed facts this mission's photo requirements name, then the
    mission's own pack rules (which read open session vocabulary, not a word list)."""
    from app.language_packs.lessons import pack_mission

    requirements = mission.photo_requirements
    labels = {obj.label.strip().casefold() for obj in objects}
    reasons, missing = [], []
    if len(labels) < requirements.min_confirmed_objects:
        reasons.append(
            f"Confirm at least {requirements.min_confirmed_objects} different objects."
        )
        missing.append("objects")
    # ``min_coloured_objects`` counts objects with any confirmed attribute, colour or other.
    described = {obj.label.strip().casefold() for obj in objects if scene_attributes(obj)}
    if len(described) < requirements.min_coloured_objects:
        reasons.append(
            "Confirm a colour, size, shape, material, pattern or state of at least one object."
            if requirements.min_coloured_objects == 1
            else "Confirm a colour, size, shape, material, pattern or state of at least "
            f"{requirements.min_coloured_objects} different objects."
        )
        missing.append("attributes")
    if requirements.min_relations and (
        len(confirmed_relations(mission, objects, relations)) < requirements.min_relations
    ):
        reasons.append(
            "Confirm where one object is on, under, next to, in front of or behind another."
        )
        missing.append("relations")
    if len(countable_groups(mission, counted_groups)) < requirements.min_counted_groups:
        reasons.append(
            f"Count a group of {requirements.min_quantity} to {requirements.max_quantity} "
            "matching objects."
        )
        missing.append("counts")
    pack_reasons = pack_mission(mission.mission_id).photo_reasons(
        mission, objects, relations, scene_attributes, counted_groups=counted_groups,
        mission_choices=mission_choices,
    )
    reasons += pack_reasons
    for reason in pack_reasons:
        missing.extend(
            ("choices",) if reason in PACK_CHOICE_REASONS
            else PACK_SHORTFALLS.get(mission.mission_id, ())
        )
    return Eligibility(not reasons, tuple(reasons), tuple(dict.fromkeys(missing)))


def scene_attributes(obj):
    """Confirmed scene semantics, independent of a finite language dictionary."""
    return [(key, {"color": "colour"}.get(key.casefold(), key.casefold()), value.strip())
            for key, value in (obj.attributes or {}).items()
            if key.casefold() in {
                "colour", "color", "size", "shape", "material", "pattern", "state",
            }
            and isinstance(value, str) and value.strip()]




def _mission_choice_supplied(mission, mission_choices):
    if not isinstance(mission_choices, dict):
        return False
    choices = mission_choices.get("missionChoices", mission_choices)
    if mission.mission_id == "M04":
        return bool(choices.get("ownership"))
    if mission.mission_id == "M05":
        return bool(choices.get("preference"))
    return False



