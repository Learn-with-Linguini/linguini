"""The contract every pack mission implements."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# (pack, level, facts, vocabulary, seed) -> {slot_id: [raw spec dicts]}; see SpecBuilder.
PlanLesson = Callable[..., dict[str, list[dict]]]
# (level, pack, facts, vocabulary, plan, accepted, *, builder_selection, session_id)
# -> (result, task, payload)
BuildLesson = Callable[..., tuple[Any, Any, dict]]
# (level, pack, facts, vocabulary, plan) -> None; raises ValueError before any model call.
CheckInputs = Callable[..., None]
# (level, result, accepted, pack) -> None; raises ValueError when the product contract changes.
CheckLesson = Callable[..., None]
# (mission, objects, relations, attributes_of, counted_groups=(), mission_choices=None)
# -> photo eligibility reasons.
PhotoReasons = Callable[..., list[str]]
# (pack, facts, vocabulary) -> vocabulary with the closed pack words the mission teaches.
MissionVocabulary = Callable[..., Any]
# (pack, level, facts, vocabulary, context) -> facts with the lesson's own facts added
# (M04's owners from the learner's choice or a role-play). ``context`` holds the saved
# mission plan's ``learner_facts`` and ``roleplay_facts``.
MissionFacts = Callable[..., Any]


def _no_check(*_args) -> None:
    return None


def _no_photo_reasons(*_args, **_kwargs) -> list[str]:
    return []


def _session_vocabulary(_pack, _facts, vocabulary):
    return vocabulary


def _scene_facts(_pack, _level, facts, _vocabulary, _context):
    return facts


@dataclass(frozen=True)
class PackMission:
    """Mission-specific code for pack-generated lessons.

    ``missions.toml`` declares what a lesson asks for (slots, constructions, labels);
    a ``PackMission`` binds confirmed facts to those slots (``plan``) and turns the
    accepted sentences into the mission's existing task contract (``build``). The
    pipeline, checks, repair, review, evaluation and release gates are shared.
    """

    mission_id: str
    plan: PlanLesson
    build: BuildLesson
    check_inputs: CheckInputs = _no_check
    check_lesson: CheckLesson = _no_check
    # Slots, per level, whose answers are built from phrase tiles instead of word tiles.
    phrase_slots: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # Replaces dictionary-based legacy photo rules, which do not fit open vocabulary.
    photo_reasons: PhotoReasons = _no_photo_reasons
    # Closed pack words (M03's number words) added before proposals and planning.
    vocabulary: MissionVocabulary = _session_vocabulary
    # Facts the lesson adds before its vocabulary and plan (M04's owners).
    facts: MissionFacts = _scene_facts


def for_level[Handler](handlers: Mapping[str, Handler], level: str, mission_id: str) -> Handler:
    """The per-level handler a mission implements, or a clear error."""
    try:
        return handlers[str(level)]
    except KeyError:
        raise ValueError(f"unsupported {mission_id} level {level}") from None
