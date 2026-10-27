"""Shared vocabulary-aware noun-phrase rules for packs with required articles."""

from pathlib import Path

import pytest

from app.language_packs.generation import (
    ApprovedVocabulary,
    CandidateSentence,
    TermUse,
    infer_term_uses,
)
from app.language_packs.loader import load_pack
from app.language_packs.validators import select_validator, validator_versions
from app.language_packs.validators.noun_phrase import NounPhraseValidator

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"
SAMPLES = Path(__file__).parents[1] / "app/language_packs/samples"


def _vocabulary(locale):
    return ApprovedVocabulary.model_validate_json(
        (SAMPLES / locale / "vocabulary.json").read_text("utf-8")
    )


def _check(locale, construction, text, roles, *, use="answer", truth=True, proposed=False):
    vocabulary = _vocabulary(locale)
    pack = load_pack(PACKS / locale / "everyday")
    role_by_fact = {fact: role for role, fact in roles.items()}
    uses = [
        use_.model_copy(update={"role": role_by_fact.get(use_.fact_id)})
        for use_ in infer_term_uses(text, vocabulary, preferred_fact_ids=set(role_by_fact))
    ]
    candidate = CandidateSentence(
        slot_id="slot", spec_id="spec", spec_use=use, truth=truth, construction_id=construction,
        text=text, origin="manual", term_uses=uses, proposed_realizations=proposed,
    )
    return NounPhraseValidator(vocabulary).validate(candidate, pack)


DOOR_RED = {"object": "object:door", "attribute": "attribute:door-red"}
SPOON_YELLOW = {"object": "object:spoon", "attribute": "attribute:spoon-yellow"}
TABLE = {"object": "object:table"}


@pytest.mark.parametrize(
    "locale,construction,text,roles,use",
    [
        # German case forms are the noun's own determiners.
        ("de-DE", "scene-existence", "Es gibt einen Löffel.", {"object": "object:spoon"}, "answer"),
        ("de-DE", "scene-location", "Der Löffel ist unter dem Tisch.",
         {"subject": "object:spoon", "reference": "object:table"}, "answer"),
        # Weak ending after a definite article is not a gender error (der rote Löffel).
        ("de-DE", "scene-location", "Der gelbe Löffel ist unter dem Tisch.",
         {"subject": "object:spoon", "attribute": "attribute:spoon-yellow"}, "answer"),
        # A predicative colour has no ending and follows the verb.
        ("de-DE", "describe-attribute", "Die Tür ist rot.", DOOR_RED, "answer"),
        ("fr-FR", "describe-attribute", "La porte est rouge.", DOOR_RED, "answer"),
        # French elision attaches the article to the noun.
        ("fr-FR", "identify-object", "l'assiette", {"object": "object:plate"}, "name"),
        ("fr-FR", "scene-location", "L'assiette est sur la table.",
         {"subject": "object:plate", "reference": "object:table"}, "answer"),
        ("es-ES", "identify-object", "Es una mesa.", TABLE, "answer"),
    ],
)
def test_valid_noun_phrases_pass(locale, construction, text, roles, use):
    result = _check(locale, construction, text, roles, use=use)
    assert result.passed, result.messages


@pytest.mark.parametrize(
    "locale,construction,text,roles,use,expected",
    [
        ("de-DE", "identify-object", "Das ist ein Tür.", {"object": "object:door"}, "answer",
         "own indefinite articles"),
        ("de-DE", "describe-attribute", "Das ist eine rotes Tür.", DOOR_RED, "answer",
         "agrees with 'Tür'"),
        ("de-DE", "describe-attribute", "Das ist ein Löffel gelber.", SPOON_YELLOW, "answer",
         "goes before the noun"),
        ("fr-FR", "identify-object", "C'est un porte.", {"object": "object:door"}, "answer",
         "own indefinite articles"),
        ("fr-FR", "describe-attribute", "C'est une jaune cuillère.", SPOON_YELLOW, "answer",
         "goes after the noun"),
        # Identifying introduces the object, so the definite article is the wrong kind.
        ("es-ES", "identify-object", "Es la mesa.", TABLE, "answer", "own indefinite articles"),
        ("fr-FR", "identify-object", "le porte", {"object": "object:door"}, "name",
         "own definite articles"),
    ],
)
def test_wrong_article_agreement_or_position_fails(locale, construction, text, roles, use,
                                                   expected):
    result = _check(locale, construction, text, roles, use=use)
    assert not result.passed
    assert any(expected in message for message in result.messages), result.messages


def test_negated_existence_may_use_a_gender_neutral_partitive():
    result = _check(
        "fr-FR", "scene-existence", "Il n'y a pas de porte.", {"object": "object:door"},
        truth=False,
    )
    assert result.passed, result.messages


def test_model_proposed_wording_is_left_to_the_content_review():
    result = _check(
        "fr-FR", "identify-object", "C'est un porte.", {"object": "object:door"}, proposed=True,
    )
    assert result.passed


def test_noun_phrase_rules_apply_only_to_packs_with_required_articles():
    for locale, language, expected in (
        ("fr-FR", "fr", True), ("de-DE", "de", True), ("es-ES", "es", True),
        ("ko-KR", "ko", False),
    ):
        pack = load_pack(PACKS / locale / "everyday")
        assert ("noun-phrase" in validator_versions(language, pack)) is expected
        validator = select_validator(language, _vocabulary(locale), pack)
        assert (NounPhraseValidator.validator_id in validator.validator_id) is expected


def test_term_use_roles_are_read_from_candidate_claims():
    vocabulary = _vocabulary("de-DE")
    door = next(term for term in vocabulary.terms if term.fact_id == "object:door")
    candidate = CandidateSentence(
        slot_id="slot", spec_id="spec", spec_use="answer", construction_id="identify-object",
        text="Das ist eine Tür.", origin="manual",
        term_uses=[TermUse(term_id=door.term_id, fact_id=door.fact_id, surface="Tür",
                           role="object")],
    )
    pack = load_pack(PACKS / "de-DE" / "everyday")
    assert NounPhraseValidator(vocabulary).validate(candidate, pack).passed
