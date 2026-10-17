"""Mission planning and per-mission photo eligibility from learner-confirmed scene facts."""

import re
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES, POSITIONS, SUPPORTED_LANGUAGES

M01_A1 = ("M01", "A1", 1)
M02_A1 = ("M02", "A1", 2)
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

# Reviewed singular (masculine, feminine) forms of the other confirmed attribute types.
# ``before`` marks French adjectives placed before the noun; ``contrasts`` are values
# clearly different in a photo, the only ones offered as distractors.
REVIEWED_ATTRIBUTES = {
    "size": {
        "big": dict(aliases=("large", "huge"), es=("grande", "grande"), fr=("grand", "grande"),
                    before=True, contrasts=("small",)),
        "small": dict(aliases=("little", "tiny"), es=("pequeño", "pequeña"),
                      fr=("petit", "petite"), before=True, contrasts=("big",)),
        "long": dict(es=("largo", "larga"), fr=("long", "longue"), before=True,
                     contrasts=("short",)),
        "short": dict(es=("corto", "corta"), fr=("court", "courte"), contrasts=("long",)),
    },
    "shape": {
        "round": dict(aliases=("circular",), es=("redondo", "redonda"), fr=("rond", "ronde"),
                      contrasts=("square", "rectangular")),
        "square": dict(es=("cuadrado", "cuadrada"), fr=("carré", "carrée"),
                       contrasts=("round",)),
        "rectangular": dict(es=("rectangular", "rectangular"),
                            fr=("rectangulaire", "rectangulaire"), contrasts=("round",)),
    },
    "material": {
        "wooden": dict(aliases=("wood",), es=("de madera",) * 2, fr=("en bois",) * 2,
                       contrasts=("metal", "plastic", "glass")),
        "metal": dict(aliases=("metallic", "steel", "iron"), es=("de metal",) * 2,
                      fr=("en métal",) * 2, contrasts=("wooden", "glass", "fabric")),
        "plastic": dict(es=("de plástico",) * 2, fr=("en plastique",) * 2,
                        contrasts=("wooden", "metal", "fabric")),
        "glass": dict(es=("de vidrio",) * 2, fr=("en verre",) * 2,
                      contrasts=("wooden", "metal", "fabric")),
        "fabric": dict(aliases=("cloth",), es=("de tela",) * 2, fr=("en tissu",) * 2,
                       contrasts=("wooden", "metal", "glass")),
        "stone": dict(es=("de piedra",) * 2, fr=("en pierre",) * 2,
                      contrasts=("wooden", "plastic", "fabric")),
    },
    "pattern": {
        "striped": dict(es=("de rayas",) * 2, fr=("rayé", "rayée"), contrasts=("spotted",)),
        "spotted": dict(aliases=("polka-dot", "dotted"), es=("de lunares",) * 2,
                        fr=("à pois",) * 2, contrasts=("striped",)),
    },
    "state": {
        "open": dict(es=("abierto", "abierta"), fr=("ouvert", "ouverte"), contrasts=("closed",)),
        "closed": dict(es=("cerrado", "cerrada"), fr=("fermé", "fermée"), contrasts=("open",)),
        "empty": dict(es=("vacío", "vacía"), fr=("vide", "vide"), contrasts=("full",)),
        "full": dict(es=("lleno", "llena"), fr=("plein", "pleine"), contrasts=("empty",)),
        "clean": dict(es=("limpio", "limpia"), fr=("propre", "propre"), contrasts=("dirty",)),
        "dirty": dict(es=("sucio", "sucia"), fr=("sale", "sale"), contrasts=("clean",)),
    },
}
ATTRIBUTE_ORDER = ("size", "shape", "material", "pattern", "state")


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


def _reviewed_value(kind, value):
    text = value.strip().casefold()
    return next((
        name for name, entry in REVIEWED_ATTRIBUTES.get(kind, {}).items()
        if text == name or text in entry.get("aliases", ())
    ), None)


def confirmed_attributes(obj):
    """Confirmed attributes with reviewed forms as ``(key, type, value)``, colour first."""
    found = []
    attributes = obj.attributes or {}
    if colour := confirmed_colour(obj):
        key = next(key for key in attributes if key.casefold() in COLOUR_ATTRIBUTE_TYPES)
        found.append((key, "colour", colour))
    for kind in ATTRIBUTE_ORDER:
        for key, value in attributes.items():
            if key.casefold() == kind and isinstance(value, str):
                if name := _reviewed_value(kind, value):
                    found.append((key, kind, name))
    return found


def agreed_attribute(kind, value, language, gender):
    """``(form agreeing with a singular noun, placed before it)``, or ``None`` when unknown."""
    if kind == "colour":
        form = agreed_colour(value, language, gender)
        return (form, False) if form else None
    entry = REVIEWED_ATTRIBUTES.get(kind, {}).get(value) or {}
    forms = entry.get(language)
    if not forms:
        return None
    masculine, feminine = forms
    form = masculine if masculine == feminine else {
        "masculine": masculine, "feminine": feminine,
    }.get(gender)
    return (form, language == "fr" and bool(entry.get("before"))) if form else None


def attribute_contrasts(kind, value):
    return REVIEWED_ATTRIBUTES.get(kind, {}).get(value, {}).get("contrasts", ())


def photo_eligibility(mission, objects, relations=(), counted_groups=()):
    """Check only the confirmed facts this mission's photo requirements name."""
    requirements = mission.photo_requirements
    labels = {obj.label.strip().casefold() for obj in objects}
    reasons = []
    if len(labels) < requirements.min_confirmed_objects:
        reasons.append(
            f"Confirm at least {requirements.min_confirmed_objects} different objects."
        )
    # ``min_coloured_objects`` counts objects with any reviewed attribute, colour or other.
    described = {obj.label.strip().casefold() for obj in objects if confirmed_attributes(obj)}
    if len(described) < requirements.min_coloured_objects:
        reasons.append(
            "Confirm a colour, size, shape, material, pattern or state of at least one object."
            if requirements.min_coloured_objects == 1
            else "Confirm a colour, size, shape, material, pattern or state of at least "
            f"{requirements.min_coloured_objects} different objects."
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
