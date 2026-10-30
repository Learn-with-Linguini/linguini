"""How I-Spy adapts to the learner's CEFR level.

Every level plays the same scene with the same confirmed words; only the clue difficulty,
the help shown and the answer format change. Unknown levels play the A1 game.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.learning_resources import get_mission_cheat_sheet

# The A0 cheatsheet that teaches exactly what I-Spy clues use: a colour after the
# object, and a position before a reference object.
ISPY_CHEAT_SHEET = ("M02", "A0", 2)


@dataclass(frozen=True)
class ISpyLevel:
    level: str
    # Phase 1 answer choices: the answer plus differently named objects; None offers all.
    clue_choices: int | None
    translation_shown: bool
    listen_first: bool
    # Phase 2: how many objects to describe, and how.
    description_tasks: int
    typing: bool
    help_collapsed: bool
    word_bank: bool
    cheat_sheet: bool
    # Matched facts a clear match needs, capped by the facts the target actually has.
    min_clear_evidence: int
    # Whether naming the right object with a detail it shares with another still counts.
    accept_ambiguous_match: bool


LEVELS = {
    "A0": ISpyLevel(
        "A0", clue_choices=3, translation_shown=True, listen_first=False,
        description_tasks=1, typing=False, help_collapsed=False, word_bank=True,
        cheat_sheet=True, min_clear_evidence=1, accept_ambiguous_match=True,
    ),
    "A1": ISpyLevel(
        "A1", clue_choices=None, translation_shown=False, listen_first=False,
        description_tasks=2, typing=True, help_collapsed=False, word_bank=False,
        cheat_sheet=False, min_clear_evidence=1, accept_ambiguous_match=False,
    ),
    "A2": ISpyLevel(
        "A2", clue_choices=None, translation_shown=False, listen_first=True,
        description_tasks=2, typing=True, help_collapsed=True, word_bank=False,
        cheat_sheet=False, min_clear_evidence=2, accept_ambiguous_match=False,
    ),
}


def ispy_level(level) -> ISpyLevel:
    return LEVELS.get(str(getattr(level, "value", level) or "").upper(), LEVELS["A1"])


def ispy_cheat_sheet(settings: ISpyLevel, language: str | None) -> dict | None:
    """The I-Spy cheatsheet reference when this level offers it and the language has it."""
    if not settings.cheat_sheet or not language:
        return None
    mission_id, practice_level, content_version = ISPY_CHEAT_SHEET
    if get_mission_cheat_sheet(mission_id, practice_level, content_version, language) is None:
        return None
    return dict(
        mission_id=mission_id, practice_level=practice_level, content_version=content_version,
    )


def word_bank(objects, words) -> list[dict]:
    """The scene's words with their English labels, once each, in object order."""
    entries = {}
    for obj, word in zip(objects, words, strict=True):
        entries.setdefault(word.display_text.casefold(), dict(
            text=word.display_text, translation=obj.label,
        ))
    return list(entries.values())
