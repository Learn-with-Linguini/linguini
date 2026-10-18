from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.language_packs.assembly import AssembledItem, Tile, assemble, is_correct, join_chunks
from app.language_packs.capabilities import lesson_plan
from app.language_packs.generation import (
    ApprovedTerm,
    ApprovedVocabulary,
    BoundSceneFacts,
    CandidateSentence,
    ConfirmedObject,
    ConfirmedSceneFacts,
    TermUse,
    ValidatorResult,
    approve,
    assess,
    check_deterministic,
    clear_validators,
    register_validator,
)
from app.language_packs.loader import load_pack
from app.language_packs.schema import Provenance, SentenceChunk, join_pack_chunks
from app.schemas.enums import PartOfSpeech

FIXTURE = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


def _candidate(
    *,
    text="Es una taza.",
    construction_id="identify-object",
    slot_id="buildIdentify-1",
    chunks=None,
    term_uses=None,
    label_uses=None,
    origin="model",
):
    return CandidateSentence(
        slot_id=slot_id,
        construction_id=construction_id,
        text=text,
        chunks=chunks or [
            SentenceChunk(text="Es", join="none"),
            SentenceChunk(text="una", join="space"),
            SentenceChunk(text="taza.", join="space"),
        ],
        term_uses=term_uses or [],
        label_uses=label_uses or [],
        origin=origin,
    )


def _facts():
    return BoundSceneFacts(
        scene_facts=ConfirmedSceneFacts(
            objects=[
                ConfirmedObject(
                    fact_id="object:cup",
                    scene_object_id=UUID(int=1),
                    label="cup",
                )
            ]
        )
    )


def _vocabulary():
    return ApprovedVocabulary(
        terms=[
            ApprovedTerm(
                term_id="cup-term",
                fact_id="object:cup",
                source_text="cup",
                target_text="taza",
                forms=["taza"],
                part_of_speech=PartOfSpeech.NOUN,
                provenance="reviewedLexicon",
            )
        ]
    )


def test_deterministic_checks_cover_slots_facts_vocabulary_labels_chunks_and_nfc():
    pack = load_pack(FIXTURE)
    plan = lesson_plan(pack, ("M01", "A0", 1))
    vocabulary = _vocabulary()
    candidate = _candidate(
        term_uses=[TermUse(term_id="cup-term", surface="taza", fact_id="object:cup")]
    )
    report = check_deterministic(candidate, plan, _facts(), vocabulary, pack)

    assert report.passed
    bad_surface = _candidate(
        text="Es una tacita.",
        chunks=[
            SentenceChunk(text="Es", join="none"),
            SentenceChunk(text="una", join="space"),
            SentenceChunk(text="tacita.", join="space"),
        ],
        term_uses=[TermUse(term_id="cup-term", surface="tacita", fact_id="object:cup")],
    )
    bad_report = check_deterministic(bad_surface, plan, _facts(), vocabulary, pack)
    assert not bad_report.passed
    assert "candidate term claim is not a reviewed form" in bad_report.failures


def test_exact_unreviewed_example_is_not_assessed_as_reviewed_or_approvable():
    pack = load_pack(FIXTURE)
    plan = lesson_plan(pack, ("M01", "A0", 1))
    candidate = _candidate()

    assessment = assess(candidate, pack)
    blocked = approve([candidate], plan, _facts(), ApprovedVocabulary(), pack)
    allowed = approve(
        [candidate], plan, _facts(), ApprovedVocabulary(), pack, allow_unassessed=True
    )

    assert assessment.status == "notAssessed"
    assert blocked.approved == []
    assert blocked.failures[0].reasons
    assert allowed.approved[0].assessment.status == "notAssessed"


def test_only_human_reviewed_exact_construction_example_grants_reviewed_form():
    pack = load_pack(FIXTURE)
    construction = next(
        item for item in pack.constructions
        if item.construction_id == "identify-object"
    )
    human_reviewed = Provenance(
        source="reviewed test copy",
        review_status="humanReviewed",
        reviewers=["reviewer"],
    )
    candidate = _candidate()
    matching_example = next(
        item for item in construction.examples if item.sentence == candidate.text
    )
    example = matching_example.model_copy(
        update={"provenance": human_reviewed}
    )
    reviewed_construction = construction.model_copy(update={"examples": [example]})
    reviewed_pack = pack.model_copy(
        update={
            "constructions": [
                reviewed_construction if item is construction else item
                for item in pack.constructions
            ]
        }
    )
    assert assess(candidate, reviewed_pack).status == "reviewedForm"
    assert assess(
        _candidate(construction_id="describe-attribute", slot_id="describeObject"),
        reviewed_pack,
    ).status == "notAssessed"


def test_vocabulary_form_match_is_not_sentence_level_review_evidence():
    pack = load_pack(FIXTURE)
    candidate = _candidate(
        text="taza",
        chunks=[SentenceChunk(text="taza", join="none")],
        term_uses=[TermUse(term_id="cup-term", surface="taza", fact_id="object:cup")],
    )

    assert assess(candidate, pack).status == "notAssessed"


def test_registered_validator_is_opt_in_and_model_output_provenance_is_generated():
    pack = load_pack(FIXTURE)
    plan = lesson_plan(pack, ("M01", "A0", 1))
    candidate = _candidate(text="Parece una taza.", chunks=[
        SentenceChunk(text="Parece", join="none"),
        SentenceChunk(text="una", join="space"),
        SentenceChunk(text="taza.", join="space"),
    ])

    class Validator:
        validator_id = "test-validator"

        def validate(self, candidate, pack):
            return ValidatorResult(passed=True)

    clear_validators()
    register_validator("es", "identify-object", Validator())
    try:
        result = approve([candidate], plan, _facts(), ApprovedVocabulary(), pack)
    finally:
        clear_validators()

    assert result.approved[0].assessment.status == "languageValidator"
    assert result.approved[0].provenance.review_status == "generated"


def test_tile_order_is_compared_by_joined_text_and_duplicate_tiles_are_allowed():
    item = AssembledItem(
        tiles=[
            Tile(tile_id="first", text="a"),
            Tile(tile_id="second", text="a"),
        ],
        answer_tile_ids=["first", "second"],
        accepted_texts=["a a"],
        word_separator="space",
        join_modes=["space", "space"],
    )

    assert is_correct(item, ["first", "second"])
    assert is_correct(item, ["second", "first"])
    assert not is_correct(item, ["first", "unknown"])


def test_assembly_preserves_chunk_join_behavior_and_non_space_separator():
    assert join_chunks is join_pack_chunks

    pack = load_pack(FIXTURE)
    plan = lesson_plan(pack, ("M01", "A0", 1))
    candidate = _candidate()
    approval = approve(
        [candidate], plan, _facts(), ApprovedVocabulary(), pack, allow_unassessed=True
    )
    item = assemble(approval.approved[0])
    no_separator_pack = pack.model_copy(
        update={
            "language": pack.language.model_copy(
                update={
                    "code": "und-x-test",
                    "locale": "und-x-test",
                    "word_separator": "none",
                    "speech": pack.language.speech.model_copy(
                        update={
                            "synthesis_locale": "und-x-test",
                            "synthesis": "none",
                            "recognition": False,
                        }
                    ),
                }
            )
        }
    )
    no_separator_candidate = _candidate(
        text="Esunataza.",
        chunks=[
            SentenceChunk(text="Es", join="none"),
            SentenceChunk(text="una", join="none"),
            SentenceChunk(text="taza.", join="none"),
        ],
    )
    no_separator_plan = lesson_plan(no_separator_pack, ("M01", "A0", 1))
    no_separator_approval = approve(
        [no_separator_candidate],
        no_separator_plan,
        _facts(),
        ApprovedVocabulary(),
        no_separator_pack,
        allow_unassessed=True,
    )
    no_separator_item = assemble(no_separator_approval.approved[0])
    no_separator = [
        SentenceChunk(text="ab", join="none"),
        SentenceChunk(text="cd", join="none"),
    ]

    assert is_correct(item, item.answer_tile_ids)
    assert no_separator_item.word_separator == "none"
    assert is_correct(no_separator_item, no_separator_item.answer_tile_ids)
    assert join_chunks(no_separator, "none") == "abcd"
    assert join_chunks(no_separator, "space") == "abcd"


def test_candidate_text_rejects_decomposed_unicode():
    with pytest.raises(ValidationError):
        _candidate(
            text="cafe\u0301",
            chunks=[SentenceChunk(text="cafe\u0301", join="none")],
        )
