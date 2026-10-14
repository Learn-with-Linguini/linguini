"""Mission selection and M01 photo eligibility from learner-confirmed scene facts."""

import os
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES, SUPPORTED_LANGUAGES

M01_A1 = ("M01", "A1", 1)

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


def lesson_mission(session_mode, profile):
    """The mission a new lesson uses, or ``None`` to keep the existing lesson path."""
    if not mission_lessons_enabled() or session_mode != SessionMode.LESSON:
        return None
    if profile["proficiency_level"] != "A1":
        return None
    if profile["target_language_code"].lower() not in SUPPORTED_LANGUAGES:
        return None
    return get_mission(*M01_A1)


def confirmed_colour(obj):
    """The object's confirmed supported colour; missing or unknown colours are never guessed."""
    for key, value in (obj.attributes or {}).items():
        if key.casefold() in COLOUR_ATTRIBUTE_TYPES and isinstance(value, str):
            colour = value.strip().casefold()
            if colour in SUPPORTED_COLOURS:
                return colour
    return None


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()


def m01_eligibility(mission, objects):
    """Check confirmed objects against the mission's photo requirements."""
    requirements = mission.photo_requirements
    labels = {obj.label.strip().casefold() for obj in objects}
    reasons = []
    if len(labels) < requirements.min_confirmed_objects:
        reasons.append(
            f"Confirm at least {requirements.min_confirmed_objects} different objects."
        )
    coloured = {obj.label.strip().casefold() for obj in objects if confirmed_colour(obj)}
    if len(coloured) < requirements.min_describable_objects:
        reasons.append("Confirm the colour of at least one object.")
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
