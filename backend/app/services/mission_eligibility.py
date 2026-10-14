"""Mission planning and per-mission photo eligibility from learner-confirmed scene facts."""

import os
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES, POSITIONS, SUPPORTED_LANGUAGES

M01_A1 = ("M01", "A1", 1)
# Implemented A1 variants in catalogue order; a lesson assesses at most two.
IMPLEMENTED_MISSIONS = {"A1": (M01_A1, ("M02", "A1", 1))}
MAX_LESSON_MISSIONS = 2

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


def mission_lessons_enabled():
    return os.getenv("MISSION_LESSONS_ENABLED", "false").strip().lower() == "true"


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
    if not mission_lessons_enabled() or session_mode != SessionMode.LESSON:
        return []
    if profile["target_language_code"].lower() not in SUPPORTED_LANGUAGES:
        return []
    keys = IMPLEMENTED_MISSIONS.get(profile["proficiency_level"], ())
    return [mission for key in keys if (mission := get_mission(*key)) is not None]


def plan_missions(candidates, objects, relations, passed_mission_ids):
    """Eligible missions for this photo, in catalogue order.

    Each mission brings one new pattern, so a second mission joins only when the
    learner already passed one of the pair in an earlier session.
    """
    eligible = [
        mission for mission in candidates
        if photo_eligibility(mission, objects, relations).eligible
    ][:MAX_LESSON_MISSIONS]
    if len(eligible) > 1 and not {m.mission_id for m in eligible} & set(passed_mission_ids):
        return eligible[:1]
    return eligible


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


def confirmed_relations(mission, objects, relations):
    """Confirmed relations of an accepted type between two differently named objects."""
    labels = {obj.id: obj.label.strip().casefold() for obj in objects}
    allowed = set(mission.photo_requirements.relations)
    return [
        relation for relation in relations
        if relation.relation in allowed
        and relation.subject_scene_object_id in labels
        and relation.reference_scene_object_id in labels
        and labels[relation.subject_scene_object_id] != labels[relation.reference_scene_object_id]
    ]


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()


def photo_eligibility(mission, objects, relations=()):
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
        reasons.append("Confirm the colour of at least one object.")
    if requirements.min_relations and (
        len(confirmed_relations(mission, objects, relations)) < requirements.min_relations
    ):
        reasons.append(
            "Confirm where one object is on, under, next to, in front of or behind another."
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
