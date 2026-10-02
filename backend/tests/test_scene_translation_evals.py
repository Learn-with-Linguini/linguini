"""Integrity checks for the translation eval, its lexicon and the judge.

The lexicon is the reference data every translation number is measured
against, so a wrong entry here quietly penalises a correct model. These tests
pin its internal consistency and check that the scorer still catches the
failures it exists to catch -- in particular the two that a fluent-looking
response hides: an article glued onto the noun, and gender judged against the
wrong reading of a word with two valid translations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.judge import (
    JudgeVerdict,
    ScriptedJudge,
    judge_translations,
    judge_vocabulary,
    summarize,
)
from evals.scene_translation.ground_truth import TranslationCase, load_cases
from evals.scene_translation.lexicon import (
    ATTRIBUTES,
    NOUNS,
    RELATIONS,
    SUPPORTED_LANGUAGES,
)
from evals.scene_translation.scoring import leading_article, normalize, score_case

EVAL_ROOT = Path(__file__).resolve().parents[1] / "evals" / "scene_translation"
CASES = load_cases(EVAL_ROOT / "cases")
CASES_BY_ID = {case.case_id: case for case in CASES}


def test_dataset_covers_both_languages() -> None:
    languages = {case.target_language for case in CASES}
    assert languages == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_reading_is_complete(language: str) -> None:
    """A reading missing an article or gender would score as a model failure."""
    for word, readings in NOUNS[language].items():
        assert readings, word
        for reading in readings:
            assert reading.translation.strip(), word
            assert reading.article.strip(), word
            assert reading.gender in {"masculine", "feminine"}, word


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_gold_translations_do_not_carry_their_article(language: str) -> None:
    """The lexicon must hold bare nouns, or it would teach the bug it checks for."""
    for word, readings in NOUNS[language].items():
        for reading in readings:
            assert leading_article(reading.translation) is None, (
                f"{language} {word}: {reading.translation!r} includes its article"
            )


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_readings_of_a_word_are_distinct(language: str) -> None:
    for word, readings in NOUNS[language].items():
        spellings = [normalize(reading.translation) for reading in readings]
        assert len(spellings) == len(set(spellings)), word


def test_both_languages_cover_the_same_vocabulary() -> None:
    """Otherwise a case is scorable in one language and silently skipped in the other."""
    assert set(NOUNS["fr"]) == set(NOUNS["es"])
    assert set(ATTRIBUTES["fr"]) == set(ATTRIBUTES["es"])
    assert set(RELATIONS["fr"]) == set(RELATIONS["es"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_every_term_in_a_case_is_in_the_lexicon(case: TranslationCase) -> None:
    language = case.target_language
    for term in case.objects:
        assert normalize(term.source) in NOUNS[language], term.source
    for term in case.attributes:
        assert normalize(term.source) in ATTRIBUTES[language], term.source
    for term in case.relationships:
        assert normalize(term.source) in RELATIONS[language], term.source


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_case_keys_are_unique(case: TranslationCase) -> None:
    keys = [term.key for term in (*case.objects, *case.attributes, *case.relationships)]
    assert len(keys) == len(set(keys))


def _response(case: TranslationCase, variant: int = 0) -> dict:
    """A fully correct response, optionally using each word's nth valid reading."""
    language = case.target_language
    objects = []
    for term in case.objects:
        readings = NOUNS[language][normalize(term.source)]
        reading = readings[min(variant, len(readings) - 1)]
        objects.append({
            "key": term.key, "source": term.source,
            "translation": reading.translation,
            "article": reading.article, "gender": reading.gender,
        })
    return {
        "objects": objects,
        "attributes": [
            {"key": t.key, "source": t.source,
             "translation": ATTRIBUTES[language][normalize(t.source)][0],
             "article": None, "gender": None}
            for t in case.attributes
        ],
        "relationships": [
            {"key": t.key, "source": t.source,
             "translation": RELATIONS[language][normalize(t.source)][0],
             "article": None, "gender": None}
            for t in case.relationships
        ],
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_a_correct_response_scores_perfectly(case: TranslationCase) -> None:
    score = score_case(case, _response(case))

    assert score.parsed
    assert score.structurally_valid
    assert score.clean
    assert score.noun_accuracy == 1.0
    assert score.article_accuracy == 1.0
    assert score.gender_accuracy == 1.0
    assert score.terms_not_in_lexicon == []


def test_an_alternative_valid_reading_is_not_penalised() -> None:
    """el estante and la estanteria are both "shelf", with different genders."""
    case = CASES_BY_ID["gender-trap-es"]
    second = score_case(case, _response(case, variant=1))

    assert second.gender_accuracy == 1.0
    assert second.article_accuracy == 1.0
    assert second.wrong_genders == []


def test_aspirated_h_blocks_elision_in_french() -> None:
    """le haricot, not l'haricot: the error a model makes from pattern alone."""
    case = CASES_BY_ID["elision-fr"]
    payload = _response(case)
    for entry in payload["objects"]:
        if entry["source"] == "bean":
            entry["article"] = "l'"

    score = score_case(case, payload)

    assert score.article_accuracy is not None and score.article_accuracy < 1.0
    assert any("bean" in message for message in score.wrong_articles)


def test_an_article_glued_onto_the_noun_is_its_own_failure() -> None:
    case = CASES_BY_ID["classroom-fr"]
    payload = _response(case)
    payload["objects"][0]["translation"] = "le " + payload["objects"][0]["translation"]

    score = score_case(case, payload)

    assert score.articles_in_translation
    assert not score.clean


def test_structural_failure_is_reported_separately_from_accuracy() -> None:
    """Dropping a supplied term is a contract break, not a translation error."""
    case = CASES_BY_ID["classroom-fr"]
    payload = _response(case)
    payload["objects"].pop()

    score = score_case(case, payload)

    assert score.parsed
    assert not score.structurally_valid
    assert score.error is not None


def test_leading_article_detection() -> None:
    assert leading_article("tasse") is None
    assert leading_article("la tasse") == "la"
    assert leading_article("l'orange") == "l'"
    assert leading_article("el agua") == "el"
    # A noun that merely starts with those letters must not be flagged.
    assert leading_article("lampe") is None
    assert leading_article("elefante") is None


def test_judge_is_asked_only_about_the_named_candidate() -> None:
    judge = ScriptedJudge({
        "spaceship": JudgeVerdict(reason="not a teachable object here", score=1, verdict="reject"),
    })

    items = judge_vocabulary(judge, "classroom-clean", ["spaceship"], scene_title="Classroom")
    system_prompt, payload = judge.calls[0]

    assert items[0].verdict.verdict == "reject"
    assert "spaceship" in payload
    # The judge must not be told which model produced the label.
    assert "gpt" not in system_prompt.lower()
    assert "gemini" not in system_prompt.lower()
    assert "claude" not in system_prompt.lower()


def test_judge_summary_separates_accepts_from_rejects() -> None:
    # Keyed on the candidate the judge is shown, not on the composite subject.
    judge = ScriptedJudge({
        "el estante": JudgeVerdict(reason="ordinary word", score=5, verdict="accept"),
        "el tacho": JudgeVerdict(reason="regionally narrow", score=2, verdict="reject"),
    })

    items = judge_translations(judge, "grocery-es", "es", [
        ("shelf", "el estante", "el", "masculine"),
        ("bin", "el tacho", "el", "masculine"),
    ])
    summary = summarize(items)

    assert summary["judged"] == 2
    assert summary["acceptRate"] == 0.5
    assert summary["meanScore"] == 3.5
    assert summary["rejected"][0]["subject"] == "bin -> el tacho"


def test_judge_summary_of_nothing_is_not_a_zero_score() -> None:
    """An empty residue means nothing needed judging, not that the model failed."""
    summary = summarize([])
    assert summary["judged"] == 0
    assert summary["acceptRate"] is None
    assert summary["meanScore"] is None
