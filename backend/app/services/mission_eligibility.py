"""Mission planning and per-mission photo eligibility from learner-confirmed scene facts."""

import re
from collections import Counter
from dataclasses import dataclass

from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES, GENDERS, POSITIONS
from app.services.mission_language_a2 import A2_ENABLED_LANGUAGES

MISSION_LANGUAGES = {"es", "fr", "de"}

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
# A0 missions use reviewed closed content, which includes Korean.
LEVEL_LANGUAGES = {
    "A0": {"es", "fr", "de", "ko"},
    "A2": A2_ENABLED_LANGUAGES | {"de", "ko"},
}

# Reviewed singular attributive colour forms for each supported lesson language.
REVIEWED_COLOURS = {
    "red": {"es": ("rojo", "roja"), "fr": ("rouge", "rouge"),
            "de": ("roter", "rote", "rotes")},
    "white": {"es": ("blanco", "blanca"), "fr": ("blanc", "blanche"),
              "de": ("weißer", "weiße", "weißes")},
    "black": {"es": ("negro", "negra"), "fr": ("noir", "noire"),
              "de": ("schwarzer", "schwarze", "schwarzes")},
    "yellow": {"es": ("amarillo", "amarilla"), "fr": ("jaune", "jaune"),
               "de": ("gelber", "gelbe", "gelbes")},
    "purple": {"es": ("morado", "morada"), "fr": ("violet", "violette"),
               "de": ("lila", "lila", "lila")},
    "gold": {"es": ("dorado", "dorada"), "fr": ("doré", "dorée"),
             "de": ("goldener", "goldene", "goldenes")},
    "silver": {"es": ("plateado", "plateada"), "fr": ("argenté", "argentée"),
               "de": ("silberner", "silberne", "silbernes")},
    "blue": {"es": ("azul", "azul"), "fr": ("bleu", "bleue"),
             "de": ("blauer", "blaue", "blaues")},
    "green": {"es": ("verde", "verde"), "fr": ("vert", "verte"),
              "de": ("grüner", "grüne", "grünes")},
    "grey": {"es": ("gris", "gris"), "fr": ("gris", "grise"),
             "de": ("grauer", "graue", "graues")},
    "gray": {"es": ("gris", "gris"), "fr": ("gris", "grise"),
             "de": ("grauer", "graue", "graues")},
    "brown": {"es": ("marrón", "marrón"), "fr": ("marron", "marron"),
              "de": ("brauner", "braune", "braunes")},
    "pink": {"es": ("rosa", "rosa"), "fr": ("rose", "rose"),
             "de": ("rosa", "rosa", "rosa")},
    "orange": {"es": ("naranja", "naranja"), "fr": ("orange", "orange"),
               "de": ("orangefarbener", "orangefarbene", "orangefarbenes")},
    "beige": {"es": ("beige", "beige"), "fr": ("beige", "beige"),
              "de": ("beige", "beige", "beige")},
}
SUPPORTED_COLOURS = set(REVIEWED_COLOURS)

# Reviewed singular (masculine, feminine) forms of the other confirmed attribute types.
# ``before`` marks French adjectives placed before the noun; ``contrasts`` are values
# clearly different in a photo, the only ones offered as distractors.
REVIEWED_ATTRIBUTES = {
    "size": {
        "big": dict(aliases=("large", "huge"), es=("grande", "grande"), fr=("grand", "grande"),
                    de=("großer", "große", "großes"), before=True, contrasts=("small",)),
        "small": dict(aliases=("little", "tiny"), es=("pequeño", "pequeña"),
                      fr=("petit", "petite"), de=("kleiner", "kleine", "kleines"),
                      before=True, contrasts=("big",)),
        "long": dict(es=("largo", "larga"), fr=("long", "longue"),
                     de=("langer", "lange", "langes"), before=True, contrasts=("short",)),
        "short": dict(es=("corto", "corta"), fr=("court", "courte"),
                      de=("kurzer", "kurze", "kurzes"), before=True, contrasts=("long",)),
    },
    "shape": {
        "round": dict(aliases=("circular",), es=("redondo", "redonda"), fr=("rond", "ronde"),
                      de=("runder", "runde", "rundes"),
                      contrasts=("square", "rectangular")),
        "square": dict(es=("cuadrado", "cuadrada"), fr=("carré", "carrée"),
                       de=("quadratischer", "quadratische", "quadratisches"),
                       contrasts=("round",)),
        "rectangular": dict(es=("rectangular", "rectangular"),
                            fr=("rectangulaire", "rectangulaire"),
                            de=("rechteckiger", "rechteckige", "rechteckiges"),
                            contrasts=("round",)),
    },
    "material": {
        "wooden": dict(aliases=("wood",), es=("de madera",) * 2, fr=("en bois",) * 2,
                       de=("aus Holz",) * 3, contrasts=("metal", "plastic", "glass")),
        "metal": dict(aliases=("metallic", "steel", "iron"), es=("de metal",) * 2,
                      fr=("en métal",) * 2, de=("aus Metall",) * 3,
                      contrasts=("wooden", "glass", "fabric")),
        "plastic": dict(es=("de plástico",) * 2, fr=("en plastique",) * 2,
                        de=("aus Plastik",) * 3, contrasts=("wooden", "metal", "fabric")),
        "glass": dict(es=("de vidrio",) * 2, fr=("en verre",) * 2, de=("aus Glas",) * 3,
                      contrasts=("wooden", "metal", "fabric")),
        "fabric": dict(aliases=("cloth",), es=("de tela",) * 2, fr=("en tissu",) * 2,
                       de=("aus Stoff",) * 3, contrasts=("wooden", "metal", "glass")),
        "stone": dict(es=("de piedra",) * 2, fr=("en pierre",) * 2,
                      de=("aus Stein",) * 3, contrasts=("wooden", "plastic", "fabric")),
    },
    "pattern": {
        "striped": dict(es=("de rayas",) * 2, fr=("rayé", "rayée"),
                        de=("gestreifter", "gestreifte", "gestreiftes"),
                        contrasts=("spotted",)),
        "spotted": dict(aliases=("polka-dot", "dotted"), es=("de lunares",) * 2,
                        fr=("à pois",) * 2, de=("gepunkteter", "gepunktete", "gepunktetes"),
                        contrasts=("striped",)),
    },
    "state": {
        "open": dict(es=("abierto", "abierta"), fr=("ouvert", "ouverte"),
                     de=("offener", "offene", "offenes"), contrasts=("closed",)),
        "closed": dict(es=("cerrado", "cerrada"), fr=("fermé", "fermée"),
                       de=("geschlossener", "geschlossene", "geschlossenes"),
                       contrasts=("open",)),
        "empty": dict(es=("vacío", "vacía"), fr=("vide", "vide"),
                      de=("leerer", "leere", "leeres"), contrasts=("full",)),
        "full": dict(es=("lleno", "llena"), fr=("plein", "pleine"),
                     de=("voller", "volle", "volles"), contrasts=("empty",)),
        "clean": dict(es=("limpio", "limpia"), fr=("propre", "propre"),
                      de=("sauberer", "saubere", "sauberes"), contrasts=("dirty",)),
        "dirty": dict(es=("sucio", "sucia"), fr=("sale", "sale"),
                      de=("schmutziger", "schmutzige", "schmutziges"), contrasts=("clean",)),
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
        for language, positions in POSITIONS.items() if language in MISSION_LANGUAGES
    }
    for relation, meaning in POSITION_MEANINGS.items()
}


def lesson_missions(session_mode, profile):
    """Implemented missions a new lesson may plan from; empty keeps the existing lesson path."""
    if session_mode != SessionMode.LESSON:
        return []
    level = str(profile["proficiency_level"] or "").strip().upper()
    languages = LEVEL_LANGUAGES.get(level, MISSION_LANGUAGES)
    language = profile["target_language_code"].lower()
    if language not in languages:
        return []
    keys = IMPLEMENTED_MISSIONS.get(level, ())
    return [
        mission for key in keys
        if (mission := get_mission(*key)) is not None
        and (
            language in {"es", "fr"}
            if mission.mission_id in {"M01", "M02", "M03", "M04"} and level == "A2"
            else language in {"es", "fr", "de", "ko"}
            if mission.mission_id == "M06" and level == "A2"
            else True
        )
    ]


def plan_missions(
    candidates, objects, relations, counted_groups=(), history=(), mission_choices=None,
):
    """Select least-planned eligible missions, returning them in catalogue order."""
    if not candidates:
        return []
    eligible = [
        mission for mission in candidates
        if photo_eligibility(
            mission, objects, relations, counted_groups, mission_choices
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


def provisional_mission_focus(candidates, objects, relations):
    """Mission candidates and the smallest suggested fact set worth confirming.

    The return value is presentation guidance over unconfirmed model output. It
    must never be used as the final mission plan or grading evidence.
    """
    counts = suggested_counted_groups(objects)
    plan = plan_missions(candidates, objects, relations, counts)
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
                if label not in seen and confirmed_colour(obj):
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

    # Give the learner a useful vocabulary set even when the provisional
    # mission itself needs fewer facts. Preserve analysis usefulness order.
    for obj in objects:
        if len(selected) >= min(5, len(objects)):
            break
        add(obj.id)
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


# What a learner can add on the review screen, in the order the screen offers it.
SHORTFALL_KINDS = ("objects", "counts", "attributes", "relations")
# A2 rules and the confirmed facts that can satisfy them.
RULE_SHORTFALLS = {
    "describeScene": ("attributes", "relations"),
    "findTarget": ("attributes", "relations"),
    "compareQuantities": ("counts",),
    "fictionalOwnership": ("attributes", "relations"),
    "requestableItem": ("objects",),
}
A0_OBJECTS_REASON = "Confirm at least 2 different objects."


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
):
    """``None`` when a mission fits; otherwise what the closest missions still need.

    A profile without implemented missions has nothing to check, so it is never short.
    """
    from app.services.shortfall_steps import mission_steps

    if not candidates or plan_missions(
        candidates, objects, relations, counted_groups, (), mission_choices
    ):
        return None
    checks = [
        (mission, photo_eligibility(mission, objects, relations, counted_groups, mission_choices))
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
        return (form, language == "de") if form else None
    entry = REVIEWED_ATTRIBUTES.get(kind, {}).get(value) or {}
    forms = entry.get(language)
    if not forms:
        return None
    form = (
        forms[0]
        if len(set(forms)) == 1
        else dict(zip(GENDERS, forms, strict=False)).get(gender)
    )
    before = (
        language == "fr" and bool(entry.get("before"))
        or language == "de" and not form.startswith("aus ")
    ) if form else False
    return (form, before) if form else None


def attribute_contrasts(kind, value):
    return REVIEWED_ATTRIBUTES.get(kind, {}).get(value, {}).get("contrasts", ())


def photo_eligibility(
    mission, objects, relations=(), counted_groups=(), mission_choices=None,
):
    """Check only the confirmed facts this mission's photo requirements name."""
    requirements = mission.photo_requirements
    labels = {obj.label.strip().casefold() for obj in objects}
    reasons, missing = [], []
    if len(labels) < requirements.min_confirmed_objects:
        reasons.append(
            f"Confirm at least {requirements.min_confirmed_objects} different objects."
        )
        missing.append("objects")
    # ``min_coloured_objects`` counts objects with any reviewed attribute, colour or other.
    described = {obj.label.strip().casefold() for obj in objects if confirmed_attributes(obj)}
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
    if requirements.eligibility_rule:
        from app.services.mission_eligibility_a2 import eligibility_reasons

        rule_reasons = eligibility_reasons(
            requirements.eligibility_rule, mission, objects, relations, counted_groups,
        )
        reasons.extend(rule_reasons)
        if rule_reasons:
            missing.extend(
                ("objects",)
                if requirements.eligibility_rule == "describeScene" and len(labels) < 3
                else RULE_SHORTFALLS.get(requirements.eligibility_rule, ())
            )
    if str(mission.practice_level) == "A0":
        a0_reasons = a0_photo_reasons(mission, objects, counted_groups, mission_choices)
        reasons += a0_reasons
        if a0_reasons:
            missing.append(
                "counts" if mission.mission_id == "M03"
                else "objects" if a0_reasons == [A0_OBJECTS_REASON]
                else "choices"
            )
    return Eligibility(not reasons, tuple(reasons), tuple(dict.fromkeys(missing)))


def _choice_value(choice, name):
    if not isinstance(choice, dict):
        return None
    return choice.get(name, choice.get({
        "scene_object_id": "sceneObjectId",
        "scene_object_ids": "sceneObjectIds",
        "chosen_object_id": "chosenObjectId",
    }.get(name, name)))


def _mission_choice_supplied(mission, mission_choices):
    if not isinstance(mission_choices, dict):
        return False
    choices = mission_choices.get("missionChoices", mission_choices)
    if mission.mission_id == "M04":
        return bool(choices.get("ownership"))
    if mission.mission_id == "M05":
        return bool(choices.get("preference"))
    return False


def a0_photo_reasons(mission, objects, counted_groups=(), mission_choices=None):
    """A0 missions need 2-3 distinct named objects, or a group of 2 or 3.

    Any confirmed object can take part: its noun comes from the reviewed lexicon or
    the session's scene translation, and a lesson whose nouns turn out unusable is
    skipped when it is built.
    """

    def named(label):
        return bool(re.sub(r"^(?:a|an|the)\s+", "", label.strip().casefold()))

    labels = {obj.label.strip().casefold() for obj in objects if named(obj.label)}
    if mission.mission_id == "M03":
        groups = [
            group for group in countable_groups(mission, counted_groups)
            if named(group.get("label", "")) or any(
                named(obj.label) for obj in objects
                if str(obj.id) in {str(item) for item in group["sceneObjectIds"]}
            )
        ]
        # Any group qualifies; the lesson counts the first one, so extra groups never block it.
        if not groups:
            return ["Count a group of 2 or 3 matching objects."]
        return []
    if len(labels) < 2:
        return [A0_OBJECTS_REASON]
    if mission.mission_id in {"M04", "M05"} and mission_choices is not None:
        choices = mission_choices.get("missionChoices", mission_choices)
        by_id = {str(obj.id): obj for obj in objects}
        if mission.mission_id == "M04":
            ownership = choices.get("ownership") or {}
            object_id = str(_choice_value(ownership, "scene_object_id") or "")
            if object_id not in by_id or not named(by_id[object_id].label):
                return ["Tell Linguini which object is yours."]
        else:
            preference = choices.get("preference") or {}
            compared = _choice_value(preference, "scene_object_ids") or []
            chosen = _choice_value(preference, "chosen_object_id")
            focus_id = str(chosen if len(compared) == 2 else compared[0] if compared else "")
            reaction = preference.get("reaction")
            if (
                focus_id not in by_id
                or not named(by_id[focus_id].label)
                or reaction == "skip"
            ):
                return ["Tell Linguini what you would choose."]
    return []


def agreed_colour(colour, language, gender):
    """The reviewed colour form agreeing with a singular noun, or ``None`` when unknown."""
    forms = REVIEWED_COLOURS.get(colour, {}).get(language)
    if forms is None:
        return None
    if len(set(forms)) == 1:
        return forms[0]
    return dict(zip(GENDERS, forms, strict=False)).get(gender)
