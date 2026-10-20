"""Mission-specific code for pack-generated lessons, keyed by mission ID.

`missions.toml` declares what a lesson asks for (slots, constructions, labels); this
registry supplies the code that binds facts to those slots and turns accepted
sentences into the existing task contract. Everything else in the pipeline
(proposals, generation, checks, repair, review, evaluation) is mission-agnostic.
A mission ID without an entry here always uses its legacy builder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackMission:
    # (pack, level, facts, vocabulary, seed) -> {slot_id: [raw spec dicts]}
    plan: Callable
    # (level, pack, facts, vocabulary, plan, accepted, *, builder_selection, session_id)
    # -> (result, task, payload)
    build: Callable
    # (level, pack, facts, vocabulary, plan); raises before any model call
    check_inputs: Callable = lambda *_args: None
    # (level, result, accepted, pack); the assembled lesson keeps its product contract
    check_lesson: Callable = lambda *_args: None
    # Slots, per level, whose answers are built from phrase tiles instead of word tiles.
    phrase_slots: dict[str, frozenset[str]] = field(default_factory=dict)
    # (mission, objects, relations, attributes_of) -> reasons; replaces dictionary-based
    # photo rules, which do not apply to open session vocabulary.
    photo_reasons: Callable = lambda *_args: []


def _m01_plan(pack, level, facts, vocabulary, seed=""):
    from .plan import m01_specs

    return m01_specs(pack, level, facts, vocabulary, seed)


def _m01_build(*args, **kwargs):
    from .adapters import build_lesson

    return build_lesson(*args, **kwargs)


def _m01_check_inputs(level, pack, facts, vocabulary, plan):
    from .adapters import validate_lesson_inputs

    validate_lesson_inputs(level, pack, facts, vocabulary, plan)


def _m01_check_lesson(level, result, accepted, pack):
    from .validation import validate_assembled_lesson

    validate_assembled_lesson(level, result, accepted, pack)


def _m01_photo_reasons(mission, objects, relations, attributes_of):
    from app.services.mission_eligibility import confirmed_relations

    if str(mission.practice_level) == "A2" and not (
        any(attributes_of(obj) for obj in objects)
        or confirmed_relations(mission, objects, relations)
    ):
        return ["Confirm an object detail or relation for the scene description."]
    return []


PACK_MISSIONS: dict[str, PackMission] = {
    "M01": PackMission(
        plan=_m01_plan,
        build=_m01_build,
        check_inputs=_m01_check_inputs,
        check_lesson=_m01_check_lesson,
        phrase_slots={"A2": frozenset({"buildSceneDescription"})},
        photo_reasons=_m01_photo_reasons,
    ),
}


def pack_mission(mission_id: str) -> PackMission:
    try:
        return PACK_MISSIONS[mission_id]
    except KeyError:
        raise ValueError(f"mission {mission_id!r} has no pack lesson implementation") from None
