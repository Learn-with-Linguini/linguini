"""M13 changes a noun's article, without replacing the noun taught in the session."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.language_packs.generation import CandidateSentence, TermUse
from app.language_packs.loader import load_pack
from app.language_packs.runtime import session_inputs
from app.language_packs.validators.noun_phrase import NounPhraseValidator

PACK = Path(__file__).parents[1] / "app/language_packs/packs/fr-FR/everyday"


def vocabulary(noun, article, gender):
    pack = load_pack(PACK)
    oid = uuid4()
    obj = SimpleNamespace(id=oid, label="object", attributes={})
    word = SimpleNamespace(id=uuid4())
    term = SimpleNamespace(key=str(oid), translation=f"{article} {noun}", article=article,
                           gender=gender, native_display=f"{article} {noun}")
    translated = SimpleNamespace(objects=[term], attributes=[], relationships=[])
    _, result = session_inputs(pack, [obj], [], [word], translated, {})
    return pack, result


@pytest.mark.parametrize(("noun", "article", "gender", "candidate"), [
    ("banane", "une", "feminine", "la banane"),
    ("vélo", "un", "masculine", "le vélo"),
    ("fruit", "un", "masculine", "le fruit"),
])
def test_indefinite_translation_is_not_mislabeled_as_definite(noun, article, gender, candidate):
    pack, terms = vocabulary(noun, article, gender)
    term = terms.terms[0]
    assert term.target_text == noun
    assert term.forms_by_key["session_phrase"] == f"{article} {noun}"
    assert "definite" not in term.forms_by_key
    assert "article_definite" not in term.forms_by_key
    result = check(pack, terms, candidate)
    assert result.passed, result.messages


def check(pack, terms, text):
    term = terms.terms[0]
    candidate = CandidateSentence(
        slot_id="chooseChunk-1", spec_id="object-1", spec_use="name",
        construction_id="noun-word-pair", text=text, origin="model",
        proposed_realizations=True,
        term_uses=[TermUse(term_id=term.term_id, fact_id=term.fact_id,
                           role="object", surface=text)],
    )
    return NounPhraseValidator(terms).validate(candidate, pack)


@pytest.mark.parametrize(("noun", "article", "gender", "candidate"), [
    ("vélo", "un", "masculine", "la bicyclette"),
    ("fruit", "un", "masculine", "les fruits"),
])
def test_model_proposals_cannot_replace_or_pluralize_the_session_noun(
    noun, article, gender, candidate,
):
    pack, terms = vocabulary(noun, article, gender)
    result = check(pack, terms, candidate)
    assert not result.passed
    assert any("session noun and number" in message for message in result.messages)


def test_definite_translation_retains_its_definite_metadata():
    _, terms = vocabulary("banane", "la", "feminine")
    assert terms.terms[0].forms_by_key["definite"] == "la banane"
    assert terms.terms[0].forms_by_key["article_definite"] == "la"


def test_indefinite_display_is_not_definite_even_when_article_metadata_is_definite():
    pack = load_pack(PACK)
    oid = uuid4()
    translated = SimpleNamespace(objects=[SimpleNamespace(
        key=str(oid), translation="vélo", article="le", gender="masculine",
        native_display="un vélo",
    )], attributes=[], relationships=[])
    _, terms = session_inputs(pack, [SimpleNamespace(id=oid, label="bicycle", attributes={})],
                              [], [SimpleNamespace(id=uuid4())], translated, {})
    assert "definite" not in terms.terms[0].forms_by_key
    assert terms.terms[0].forms_by_key["session_phrase"] == "un vélo"
    assert check(pack, terms, "le vélo").passed
