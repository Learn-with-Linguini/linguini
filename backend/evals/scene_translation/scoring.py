"""Scoring for the scene-translation evaluation dataset.

Structural validity reuses ``validate_translation_terms`` -- the same check the
production translator runs -- so a response that scores as structurally valid
here is one the app would have accepted.

The accuracy metrics are deliberately split into three, because a translation
can fail in three unrelated ways and the app breaks differently in each:

``noun accuracy``
    Is the word right at all?

``article accuracy``
    Is the definite article right *for the word the model chose*? The article
    is displayed next to the noun when teaching, so a wrong one is visible to
    the learner on every card.

``gender accuracy``
    Same, for grammatical gender, which drives later grammar tasks.

Article and gender are always judged against the chosen reading, never against
one canonical answer. *el estante* and *la estantería* are both "shelf", and
marking the second one's gender wrong because the first is listed first would
penalise a correct translation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.features.translation.schemas import SceneTranslationResult, TranslatedTerm
from app.ai.features.translation.validation import (
    SceneTranslationError,
    validate_translation_terms,
)

from .ground_truth import TranslationCase
from .lexicon import ATTRIBUTES, NOUNS, RELATIONS, Reading

_ARTICLE_PREFIXES = (
    "le ", "la ", "les ", "l'", "un ", "une ",
    "el ", "los ", "las ", "un ", "una ",
)


def normalize(text: str) -> str:
    """Casefold and collapse whitespace, keeping accents and apostrophes."""
    text = unicodedata.normalize("NFC", text).casefold().strip()
    return re.sub(r"\s+", " ", text)


def fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _matches(candidate: str, expected: str) -> bool:
    """Compare leniently on accents; models drop them and learners still read it."""
    left, right = normalize(candidate), normalize(expected)
    if left == right:
        return True
    return fold_accents(left) == fold_accents(right)


def leading_article(translation: str) -> str | None:
    """The article a model wrongly glued onto the noun, if any.

    The schema keeps the article in its own field. "la tasse" in the
    ``translation`` field breaks the card layout and any later grammar task
    that needs the bare noun, so it is counted as its own failure rather than
    as a wrong translation.
    """
    text = normalize(translation)
    for prefix in _ARTICLE_PREFIXES:
        if text.startswith(prefix):
            return prefix.strip()
    return None


@dataclass
class TermOutcome:
    key: str
    source: str
    returned: str
    expected: str | None = None
    translation_ok: bool = False
    article_ok: bool | None = None
    gender_ok: bool | None = None
    article_in_translation: str | None = None
    in_lexicon: bool = True


@dataclass
class TranslationCaseScore:
    case_id: str
    target_language: str
    tags: list[str] = field(default_factory=list)

    parsed: bool = False
    structurally_valid: bool = False
    error: str | None = None

    noun_accuracy: float | None = None
    article_accuracy: float | None = None
    gender_accuracy: float | None = None
    attribute_accuracy: float | None = None
    relation_accuracy: float | None = None
    elision_accuracy: float | None = None

    articles_in_translation: list[str] = field(default_factory=list)
    wrong_nouns: list[str] = field(default_factory=list)
    wrong_articles: list[str] = field(default_factory=list)
    wrong_genders: list[str] = field(default_factory=list)
    terms_not_in_lexicon: list[str] = field(default_factory=list)

    outcomes: list[TermOutcome] = field(default_factory=list)

    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def clean(self) -> bool:
        return (
            self.structurally_valid
            and not self.articles_in_translation
            and not self.wrong_nouns
            and not self.wrong_articles
            and not self.wrong_genders
        )


def _ratio(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _pick_reading(term: TranslatedTerm, readings: Sequence[Reading]) -> Reading | None:
    """The gold reading the model appears to have chosen, if any."""
    for reading in readings:
        if _matches(term.translation, reading.translation):
            return reading
    return None


def score_case(
    case: TranslationCase,
    payload_out: Mapping[str, Any] | str | bytes,
    *,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> TranslationCaseScore:
    score = TranslationCaseScore(
        case_id=case.case_id,
        target_language=case.target_language,
        tags=list(case.tags),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    try:
        if isinstance(payload_out, (str, bytes)):
            result = SceneTranslationResult.model_validate_json(payload_out)
        else:
            result = SceneTranslationResult.model_validate(payload_out)
    except Exception as exc:  # noqa: BLE001 - any parse failure fails the case
        score.error = f"{type(exc).__name__}: {exc}"
        return score

    score.parsed = True

    # The production check: keys and sources preserved, articles present on
    # objects and absent everywhere else.
    try:
        validate_translation_terms(case.payload(), result)
        score.structurally_valid = True
    except SceneTranslationError as exc:
        score.error = str(exc)

    _score_nouns(case, result, score)
    _score_plain(case, result, score)
    return score


def _score_nouns(
    case: TranslationCase, result: SceneTranslationResult, score: TranslationCaseScore
) -> None:
    gold = NOUNS[case.target_language]
    sources = {term.key: term.source for term in case.objects}

    translation_flags: list[bool] = []
    article_flags: list[bool] = []
    gender_flags: list[bool] = []
    elision_flags: list[bool] = []

    for term in result.objects:
        source = sources.get(term.key, term.source)
        readings = gold.get(normalize(source))
        outcome = TermOutcome(
            key=term.key, source=source, returned=term.translation,
            in_lexicon=readings is not None,
        )

        glued = leading_article(term.translation)
        if glued is not None:
            outcome.article_in_translation = glued
            score.articles_in_translation.append(f"{source} -> {term.translation}")

        if readings is None:
            score.terms_not_in_lexicon.append(source)
            score.outcomes.append(outcome)
            continue

        outcome.expected = readings[0].translation
        chosen = _pick_reading(term, readings)
        outcome.translation_ok = chosen is not None
        translation_flags.append(outcome.translation_ok)
        if chosen is None:
            score.wrong_nouns.append(
                f"{source}: got {term.translation!r}, expected one of "
                f"{[r.translation for r in readings]}"
            )
            score.outcomes.append(outcome)
            continue

        # Judged against the reading the model chose, not against readings[0].
        outcome.article_ok = _matches(term.article or "", chosen.article)
        article_flags.append(outcome.article_ok)
        if not outcome.article_ok:
            score.wrong_articles.append(
                f"{source}: got {term.article!r}, expected {chosen.article!r} "
                f"for {chosen.translation!r}"
            )

        outcome.gender_ok = (term.gender or "") == chosen.gender
        gender_flags.append(outcome.gender_ok)
        if not outcome.gender_ok:
            score.wrong_genders.append(
                f"{source}: got {term.gender!r}, expected {chosen.gender!r} "
                f"for {chosen.translation!r}"
            )

        # Elision is where French articles are most often wrong in both
        # directions: l'orange but le haricot.
        if case.target_language == "fr":
            elision_flags.append(outcome.article_ok)

        score.outcomes.append(outcome)

    score.noun_accuracy = _ratio(translation_flags)
    score.article_accuracy = _ratio(article_flags)
    score.gender_accuracy = _ratio(gender_flags)
    if case.target_language == "fr":
        score.elision_accuracy = _ratio(elision_flags)


def _score_plain(
    case: TranslationCase, result: SceneTranslationResult, score: TranslationCaseScore
) -> None:
    """Attributes and relationships: translation only, no article or gender."""
    for field_name, gold_table, setter in (
        ("attributes", ATTRIBUTES[case.target_language], "attribute_accuracy"),
        ("relationships", RELATIONS[case.target_language], "relation_accuracy"),
    ):
        sources = {
            term.key: term.source for term in getattr(case, field_name)
        }
        flags: list[bool] = []
        for term in getattr(result, field_name):
            source = normalize(sources.get(term.key, term.source))
            accepted = gold_table.get(source)
            if accepted is None:
                score.terms_not_in_lexicon.append(source)
                continue
            ok = any(_matches(term.translation, option) for option in accepted)
            flags.append(ok)
            if not ok:
                score.wrong_nouns.append(
                    f"{source}: got {term.translation!r}, expected one of {list(accepted)}"
                )
        setattr(score, setter, _ratio(flags))
