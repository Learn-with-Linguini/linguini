"""Provider-neutral, deterministic validation for generated I-Spy clues.

No SDK imports: the same rules run regardless of which adapter produced the
response. ``ISpyClueGenerationError`` stays a ``SceneAnalysisError`` so the
workflow's deterministic clue-round fallback is unchanged.

Includes deterministic answer-leakage detection: a clue may describe its
answer but must never name it, in either the English source label or the
target-language translation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.ai.features.ispy_clues.schemas import ISpyClueResult
from app.services.scene_analysis import SceneAnalysisError


class ISpyClueGenerationError(SceneAnalysisError):
    """The provider did not return safe, scene-grounded I-Spy clues."""


# Leading determiners dropped from the answer term before matching, so
# "la tasse" still leaks when the clue says "tasse".
_LEADING_ARTICLES = frozenset(
    "the a an le la les l un une des du de el los las un una unos unas".split()
)
_NON_ALPHANUMERIC = re.compile(r"[^\w]|_", re.UNICODE)
_CLUE_OPENINGS = ("i spy", "je vois", "veo ")


def _tokens(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return [
        token
        for token in _NON_ALPHANUMERIC.sub(" ", stripped).casefold().split()
        if token
    ]


def _answer_term_tokens(term: str) -> list[str]:
    tokens = _tokens(term)
    while tokens and tokens[0] in _LEADING_ARTICLES:
        tokens = tokens[1:]
    return tokens


def _contains_subsequence(tokens: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(tokens):
        return False
    return any(
        tokens[start : start + len(needle)] == needle
        for start in range(len(tokens) - len(needle) + 1)
    )


def _check_answer_leakage(payload: dict[str, Any], clue) -> None:
    objects = {row["key"]: row for row in payload.get("objects", [])}
    answer = objects.get(clue.answer_object_key)
    if answer is None:
        return  # the unknown-answer check below reports this
    clue_tokens = _tokens(clue.clue)
    translation_tokens = _tokens(clue.clue_translation)
    for term in (answer.get("source", ""), answer.get("translation", "")):
        needle = _answer_term_tokens(term)
        if not needle:
            continue
        if _contains_subsequence(clue_tokens, needle) or _contains_subsequence(
            translation_tokens, needle
        ):
            raise ISpyClueGenerationError("I-Spy clue names its own answer.")


def validate_ispy_clues(payload: dict[str, Any], result: ISpyClueResult) -> None:
    object_keys = {row["key"] for row in payload.get("objects", [])}
    relationship_keys = {row["key"] for row in payload.get("relationships", [])}
    answers = set()
    for clue in result.clues:
        if clue.answer_object_key not in object_keys:
            raise ISpyClueGenerationError("I-Spy clue answer is not in the supplied scene.")
        if clue.object_keys != [clue.answer_object_key]:
            raise ISpyClueGenerationError("Each I-Spy clue must reference its answer object only.")
        if not set(clue.relationship_keys) <= relationship_keys:
            raise ISpyClueGenerationError("I-Spy clue used a relationship outside the scene.")
        if clue.answer_object_key in answers:
            raise ISpyClueGenerationError("I-Spy clues must have different answers.")
        answers.add(clue.answer_object_key)
        if clue.clue.casefold().lstrip().startswith(_CLUE_OPENINGS):
            raise ISpyClueGenerationError("I-Spy clue must contain only the phrase ending.")
        if clue.clue_translation.casefold().lstrip().startswith(_CLUE_OPENINGS):
            raise ISpyClueGenerationError(
                "I-Spy clue translation must contain only the phrase ending."
            )
        _check_answer_leakage(payload, clue)
