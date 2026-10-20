"""Declarative per-construction pack checks and the shared validator that runs them."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.language_packs.evaluation import evaluation_identity
from app.language_packs.fingerprint import pack_fingerprint
from app.language_packs.generation import ApprovedVocabulary, CandidateSentence, assess
from app.language_packs.loader import load_pack
from app.language_packs.schema import Construction, ConstructionCheck
from app.language_packs.validators import select_validator, validator_versions
from app.language_packs.validators.checks import PackChecksValidator
from app.language_packs.validators.noun_phrase import NounPhraseValidator

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"
LOCALES = ["es-ES", "fr-FR", "de-DE", "ko-KR"]


def _use(example, construction_id):
    """Best-effort spec use for a reference example (examples record purposes, not uses)."""
    if set(example.purposes) & {"matchName", "chooseName", "listenSelect"}:
        return "name"
    if example.sentence.endswith("?"):
        if construction_id in {"describe-attribute", "scene-location"}:
            return "followup"
        return "question"
    return "answer"


def _candidate(construction_id, text, use="answer", truth=True):
    return CandidateSentence(
        slot_id="slot", spec_id="spec", spec_use=use, truth=truth,
        construction_id=construction_id, text=text, origin="manual",
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_checks_never_reject_a_pack_example_or_alternative(locale):
    pack = load_pack(PACKS / locale / "everyday")
    assert any(construction.checks for construction in pack.constructions)
    failures = [
        (construction.construction_id, check.check_id, text)
        for construction in pack.constructions
        for example in construction.examples
        # Bare detail options are chosen from vocabulary, never generated as sentences.
        if "chooseAttribute" not in example.purposes
        for text in [example.sentence, *example.accepted_alternatives]
        for check in construction.checks
        if check.applies(_use(example, construction.construction_id), example.truth)
        and not check.passes(text)
    ]
    assert not failures


@pytest.mark.parametrize(
    "locale,construction_id,use,truth,text",
    [
        ("fr-FR", "scene-location", "answer", True, "La fenêtre est à côté de le téléphone."),
        ("fr-FR", "identify-object", "answer", True, "Une clé c'est."),
        ("fr-FR", "scene-existence", "answer", False, "Il y a un téléphone."),
        ("de-DE", "scene-location", "answer", True, "Das Fenster ist neben das Handy."),
        ("de-DE", "identify-object", "answer", True, "Ein Schlüssel das ist."),
        ("ko-KR", "connected-description", "connected", True, "빨간 컵이 있고 책도 있다."),
        ("ko-KR", "identify-object", "answer", True, "예요 열쇠."),
    ],
)
def test_checks_reject_known_surface_mistakes(locale, construction_id, use, truth, text):
    pack = load_pack(PACKS / locale / "everyday")
    result = PackChecksValidator().validate(_candidate(construction_id, text, use, truth), pack)
    assert not result.passed
    assert all("(pack check " in message for message in result.messages)


def test_check_filters_use_truth_and_typographic_apostrophes():
    check = ConstructionCheck(
        check_id="negation", message="Negate it.", must_contain=[r"n'y a pas"],
        except_uses=["falseFirst"], truth=False,
    )
    assert not check.applies("answer", True)
    assert not check.applies("falseFirst", False)
    assert check.applies("answer", False)
    assert check.applies(None, False)
    assert check.passes("Il n’y a pas de téléphone.")


@pytest.mark.parametrize(
    "fields,error",
    [
        ({}, "needs must_contain or must_not_contain"),
        ({"must_contain": ["("]}, "invalid pattern"),
        ({"must_contain": ["x"], "uses": ["name"], "except_uses": ["name"]}, "includes and"),
    ],
)
def test_invalid_checks_are_rejected_when_the_pack_loads(fields, error):
    with pytest.raises(ValidationError, match=error):
        ConstructionCheck(check_id="bad", message="Bad.", **fields)


def test_duplicate_check_ids_are_rejected():
    check = dict(check_id="same", message="M.", must_contain=["x"])
    pack = load_pack(PACKS / "fr-FR" / "everyday")
    data = pack.constructions[0].model_dump(mode="python", by_alias=False)
    with pytest.raises(ValidationError, match="unique"):
        Construction.model_validate({**data, "checks": [check, check]})


def test_spanish_targeted_validator_and_pack_checks_both_run():
    pack = load_pack(PACKS / "es-ES" / "everyday")
    vocabulary = ApprovedVocabulary()
    assert validator_versions("es", pack) == {
        "es": "es-targeted@6", "noun-phrase": NounPhraseValidator.validator_id,
        "pack-checks": PackChecksValidator.validator_id,
    }
    assert validator_versions("es") == {"es": "es-targeted@6"}
    validator = select_validator("es", vocabulary, pack)
    assert validator.validator_id == (
        f"es-targeted@6+{NounPhraseValidator.validator_id}+{PackChecksValidator.validator_id}"
    )
    # Proposal mode runs only es.py's light checks; the pack's hay frame still applies.
    candidate = _candidate("scene-existence", "Existe una taza roja.").model_copy(
        update={"proposed_realizations": True}
    )
    assessment = assess(candidate, pack, vocabulary)
    assert assessment.passed is False
    assert any("existence-hay" in message for message in assessment.messages)


def test_editing_a_check_invalidates_cache_and_evaluation_identity():
    pack = load_pack(PACKS / "fr-FR" / "everyday")
    constructions = [
        item.model_copy(update={"checks": item.checks[1:]})
        if item.construction_id == "identify-object"
        else item
        for item in pack.constructions
    ]
    changed = pack.model_copy(update={"constructions": constructions})
    ids = ["identify-object"]
    assert pack_fingerprint(pack, ids, "g")["guidance_sha256"] != pack_fingerprint(
        changed, ids, "g"
    )["guidance_sha256"]
    assert evaluation_identity(pack, "A0").generation_content_sha256 != evaluation_identity(
        changed, "A0"
    ).generation_content_sha256


def test_korean_targeted_validator_runs_with_pack_checks():
    pack = load_pack(PACKS / "ko-KR" / "everyday")
    assert validator_versions("ko", pack) == {
        "ko": "ko-targeted@1", "pack-checks": PackChecksValidator.validator_id,
    }
    assessment = assess(_candidate("identify-object", "컵이에요."), pack, ApprovedVocabulary())
    assert assessment.status == "languageValidator"
    assert assessment.passed is True
    # A final consonant takes 이에요 and 을, never 예요 or 를.
    for wrong in ("문예요.", "책를 찾아보세요."):
        assessment = assess(_candidate("identify-object", wrong), pack, ApprovedVocabulary())
        assert assessment.passed is False, wrong
    for right in ("의자예요.", "가방을 찾아보세요.", "탁자를 찾아보세요."):
        assessment = assess(_candidate("identify-object", right), pack, ApprovedVocabulary())
        assert assessment.passed is True, right
