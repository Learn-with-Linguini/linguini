"""Mission planning and per-mission photo eligibility from learner-confirmed scene facts."""

import re
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES, POSITIONS, SUPPORTED_LANGUAGES

M01_A1 = ("M01", "A1", 2)
M02_A1 = ("M02", "A1", 1)
M03_A1 = ("M03", "A1", 1)
# Implemented A1 variants in catalogue order; a lesson assesses at most three.
IMPLEMENTED_MISSIONS = {"A1": (M01_A1, M02_A1, M03_A1)}
MAX_LESSON_MISSIONS = 3

# Reviewed singular (masculine, feminine) colour forms for each supported lesson language.
REVIEWED_COLOURS = {
    "red": {"es": ("rojo", "roja"), "fr": ("rouge", "rouge")},
    "white": {"es": ("blanco", "blanca"), "fr": ("blanc", "blanche")},
    "black": {"es": ("negro", "negra"), "fr": ("noir", "noire")},
    "yellow": {"es": ("amarillo", "amarilla"), "fr": ("jaune", "jaune")},
    "purple": {"es": ("morado", "morada"), "fr": ("violet", "violette")},
    "gold": {"es": ("dorado", "dorada"), "fr": ("doré", "dorée")},
    "silver": {"es": ("plateado", "plateada"), "fr": ("argenté", "argentée")},
    "blue": {"es": ("azul", "azul"), "fr": ("bleu", "bleue")},
    "green": {"es": ("verde", "verde"), "fr": ("vert", "verte")},
    "grey": {"es": ("gris", "gris"), "fr": ("gris", "grise")},
    "gray": {"es": ("gris", "gris"), "fr": ("gris", "grise")},
    "brown": {"es": ("marrón", "marrón"), "fr": ("marron", "marron")},
    "pink": {"es": ("rosa", "rosa"), "fr": ("rose", "rose")},
    "orange": {"es": ("naranja", "naranja"), "fr": ("orange", "orange")},
    "beige": {"es": ("beige", "beige"), "fr": ("beige", "beige")},
}
SUPPORTED_COLOURS = set(REVIEWED_COLOURS)


# Relation types with reviewed location expressions, keyed by the I-Spy position meanings.
POSITION_MEANINGS = {
    "on": "on", "under": "under", "next_to": "next to",
    "in_front_of": "in front of", "behind": "behind",
}
REVIEWED_POSITIONS = {
    relation: {
        language: next(expression for expression, sense, _ in positions if sense == meaning)
        for language, positions in POSITIONS.items()
    }
    for relation, meaning in POSITION_MEANINGS.items()
}


def lesson_missions(session_mode, profile):
    """Implemented missions a new lesson may plan from; empty keeps the existing lesson path."""
    if session_mode != SessionMode.LESSON:
        return []
    if profile["target_language_code"].lower() not in SUPPORTED_LANGUAGES:
        return []
    keys = IMPLEMENTED_MISSIONS.get(profile["proficiency_level"], ())
    return [mission for key in keys if (mission := get_mission(*key)) is not None]


def plan_missions(candidates, objects, relations, counted_groups=()):
    """Every mission this photo supports, in catalogue order."""
    return [
        mission for mission in candidates
        if photo_eligibility(mission, objects, relations, counted_groups).eligible
    ][:MAX_LESSON_MISSIONS]


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


def confirmed_colour(obj):
    """The object's confirmed supported colour; missing or unknown colours are never guessed."""
    for key, value in (obj.attributes or {}).items():
        if key.casefold() in COLOUR_ATTRIBUTE_TYPES and isinstance(value, str):
            colour = value.strip().casefold()
            if colour in SUPPORTED_COLOURS:
                return colour
    return None


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


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()


def saved_counted_groups(draft):
    """The learner-confirmed counts saved with the session's review."""
    return list((draft or {}).get("countedGroups") or [])


def countable_groups(mission, counted_groups):
    requirements = mission.photo_requirements
    return [
        group for group in counted_groups
        if requirements.min_quantity <= group["quantity"] <= requirements.max_quantity
    ]


def photo_eligibility(mission, objects, relations=(), counted_groups=()):
    """Check only the confirmed facts this mission's photo requirements name."""
    requirements = mission.photo_requirements
    labels = {obj.label.strip().casefold() for obj in objects}
    reasons = []
    if len(labels) < requirements.min_confirmed_objects:
        reasons.append(
            f"Confirm at least {requirements.min_confirmed_objects} different objects."
        )
    coloured = {obj.label.strip().casefold() for obj in objects if confirmed_colour(obj)}
    if len(coloured) < requirements.min_coloured_objects:
        reasons.append(
            "Confirm the colour of at least one object."
            if requirements.min_coloured_objects == 1
            else f"Confirm the colours of at least {requirements.min_coloured_objects} "
            "different objects."
        )
    if requirements.min_relations and (
        len(confirmed_relations(mission, objects, relations)) < requirements.min_relations
    ):
        reasons.append(
            "Confirm where one object is on, under, next to, in front of or behind another."
        )
    if len(countable_groups(mission, counted_groups)) < requirements.min_counted_groups:
        reasons.append(
            f"Count a group of {requirements.min_quantity} to {requirements.max_quantity} "
            "matching objects."
        )
    return Eligibility(not reasons, tuple(reasons))


def agreed_colour(colour, language, gender):
    """The reviewed colour form agreeing with a singular noun, or ``None`` when unknown."""
    forms = REVIEWED_COLOURS.get(colour, {}).get(language)
    if forms is None:
        return None
    masculine, feminine = forms
    if masculine == feminine:
        return masculine
    return {"masculine": masculine, "feminine": feminine}.get(gender)
