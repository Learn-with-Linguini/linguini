"""Typed, model-independent language-pack generation and assessment stages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal, Protocol
from unicodedata import normalize
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import PartOfSpeech, SceneRelationType
from app.schemas.tasks import ContractId

from .assembly import join_chunks
from .capabilities import LessonPlan
from .schema import (
    GuidanceBundle,
    LanguagePack,
    Provenance,
    SentenceChunk,
    WordSeparator,
)

type LinguisticValue = str | bool | int | list[str]
type LinguisticMetadata = dict[ContractId, LinguisticValue]
type SceneAttributeKind = Literal["colour", "size", "shape", "material", "pattern", "state"]
type VocabularyProvenance = Literal["reviewedLexicon", "catalog", "sessionTranslation"]
type CandidateOrigin = Literal["model", "reviewedForm", "manual"]
type AssessmentStatus = Literal[
    "notAssessed", "unreviewedExample", "reviewedForm",
    "languageValidator", "humanApproved",
]


def fact_id(kind: Literal["object", "attribute", "relation", "count"], *parts: object) -> str:
    expected_parts = {"object": 1, "attribute": 2, "relation": 3, "count": 1}
    if len(parts) != expected_parts[kind]:
        raise ValueError(f"{kind} fact IDs require {expected_parts[kind]} component(s)")
    return ":".join((kind, *(str(part) for part in parts)))


class ConfirmedObject(ApiModel):
    fact_id: NonEmptyText
    scene_object_id: UUID
    label: NonEmptyText
    marker: int | None = None


class ConfirmedAttribute(ApiModel):
    fact_id: NonEmptyText
    object_fact_id: NonEmptyText
    kind: SceneAttributeKind
    value: NonEmptyText


class ConfirmedRelation(ApiModel):
    fact_id: NonEmptyText
    subject_fact_id: NonEmptyText
    reference_fact_id: NonEmptyText
    relation: SceneRelationType


class ConfirmedCount(ApiModel):
    fact_id: NonEmptyText
    object_fact_ids: Annotated[list[NonEmptyText], Field(min_length=1)]
    quantity: Annotated[int, Field(ge=1, le=20)]


class ConfirmedSceneFacts(ApiModel):
    objects: list[ConfirmedObject] = Field(default_factory=list)
    attributes: list[ConfirmedAttribute] = Field(default_factory=list)
    relations: list[ConfirmedRelation] = Field(default_factory=list)
    counted_groups: list[ConfirmedCount] = Field(default_factory=list)

    @property
    def all_fact_ids(self) -> set[str]:
        return {
            fact.fact_id
            for group in (self.objects, self.attributes, self.relations, self.counted_groups)
            for fact in group
        }

    @model_validator(mode="after")
    def validate_fact_references(self) -> ConfirmedSceneFacts:
        all_ids = [
            fact.fact_id
            for group in (self.objects, self.attributes, self.relations, self.counted_groups)
            for fact in group
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("scene fact IDs must be unique")
        object_ids = {fact.fact_id for fact in self.objects}
        references = [
            *(fact.object_fact_id for fact in self.attributes),
            *(fact.subject_fact_id for fact in self.relations),
            *(fact.reference_fact_id for fact in self.relations),
            *(object_id for fact in self.counted_groups for object_id in fact.object_fact_ids),
        ]
        if unknown := set(references) - object_ids:
            raise ValueError(f"scene facts reference unknown objects: {sorted(unknown)}")
        if any(fact.subject_fact_id == fact.reference_fact_id for fact in self.relations):
            raise ValueError("relation subjects and references must differ")
        return self


class BoundStatement(ApiModel):
    statement_id: NonEmptyText
    construction_id: ContractId
    bindings: dict[ContractId, NonEmptyText]
    truth: bool


class BoundSceneFacts(ApiModel):
    scene_facts: ConfirmedSceneFacts
    statements: list[BoundStatement] = Field(default_factory=list)

    @property
    def all_fact_ids(self) -> set[str]:
        return self.scene_facts.all_fact_ids | {
            statement.statement_id for statement in self.statements
        }

    @model_validator(mode="after")
    def validate_statements(self) -> BoundSceneFacts:
        statement_ids = [statement.statement_id for statement in self.statements]
        if len(statement_ids) != len(set(statement_ids)):
            raise ValueError("bound statement IDs must be unique")
        for statement in self.statements:
            if unknown := set(statement.bindings.values()) - self.scene_facts.all_fact_ids:
                raise ValueError(f"statement bindings reference unknown facts: {sorted(unknown)}")
        return self


class ApprovedTerm(ApiModel):
    term_id: ContractId
    fact_id: NonEmptyText
    source_text: NonEmptyText
    target_text: NonEmptyText
    forms: list[NonEmptyText] = Field(min_length=1)
    part_of_speech: PartOfSpeech
    vocabulary_item_id: UUID | None = None
    provenance: VocabularyProvenance
    romanization: str | None = None
    linguistic: LinguisticMetadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_forms(self) -> ApprovedTerm:
        if len(self.forms) != len(set(self.forms)):
            raise ValueError("approved term forms must be unique")
        if any(normalize("NFC", form) != form for form in self.forms):
            raise ValueError("approved term forms must be NFC")
        return self


class ApprovedVocabulary(ApiModel):
    terms: list[ApprovedTerm] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_terms(self) -> ApprovedVocabulary:
        ids = [term.term_id for term in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("approved term IDs must be unique")
        return self


class TermUse(ApiModel):
    term_id: ContractId
    surface: NonEmptyText
    fact_id: NonEmptyText


class CandidateSentence(ApiModel):
    slot_id: NonEmptyText
    construction_id: ContractId
    text: NonEmptyText
    chunks: list[SentenceChunk]
    term_uses: list[TermUse] = Field(default_factory=list)
    label_uses: list[ContractId] = Field(default_factory=list)
    origin: CandidateOrigin

    @model_validator(mode="after")
    def validate_nfc(self) -> CandidateSentence:
        if normalize("NFC", self.text) != self.text:
            raise ValueError("candidate text must be NFC")
        return self


class DeterministicReport(ApiModel):
    scope: str = "Structural checks only; not proof of meaning or grammaticality."
    unknown_slot: bool
    construction_matches_slot: bool
    fact_references_valid: bool
    term_references_valid: bool
    term_surfaces_are_reviewed: bool
    term_surfaces_present: bool
    labels_match_slot_and_pack: bool
    label_texts_present: bool
    chunks_reconstruct: bool
    text_is_nfc: bool
    failures: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


class LinguisticAssessment(ApiModel):
    status: AssessmentStatus
    validator_id: str | None = None
    passed: bool | None = None
    messages: list[str] = Field(default_factory=list)


class ValidatorResult(ApiModel):
    passed: bool
    messages: list[str] = Field(default_factory=list)


class CandidateGenerator(Protocol):
    def generate(
        self,
        plan: LessonPlan,
        facts: BoundSceneFacts,
        vocabulary: ApprovedVocabulary,
        guidance: GuidanceBundle,
    ) -> Sequence[CandidateSentence]: ...


class LinguisticValidator(Protocol):
    validator_id: str

    def validate(self, candidate: CandidateSentence, pack: LanguagePack) -> ValidatorResult: ...


class ApprovedSentence(ApiModel):
    candidate: CandidateSentence
    assessment: LinguisticAssessment
    deterministic_report: DeterministicReport
    provenance: Provenance
    word_separator: WordSeparator


class CandidateFailure(ApiModel):
    candidate: CandidateSentence
    assessment: LinguisticAssessment
    deterministic_report: DeterministicReport
    reasons: list[str]


class ApprovalResult(ApiModel):
    approved: list[ApprovedSentence]
    failures: list[CandidateFailure]


_VALIDATORS: dict[tuple[str, str], LinguisticValidator] = {}


def register_validator(
    language: str, construction_id: str, validator: LinguisticValidator
) -> None:
    _VALIDATORS[(language, construction_id)] = validator


def clear_validators() -> None:
    _VALIDATORS.clear()


def check_deterministic(
    candidate: CandidateSentence,
    plan: LessonPlan,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    pack: LanguagePack,
) -> DeterministicReport:
    slot = next((item for item in plan.slots if item.slot_id == candidate.slot_id), None)
    by_term = {term.term_id: term for term in vocabulary.terms}
    by_label = {label.semantic: label for label in pack.labels}
    failures = []

    unknown_slot = slot is None
    if unknown_slot:
        failures.append("unknown slot")
    construction_matches = slot is not None and candidate.construction_id == slot.construction_id
    if not construction_matches:
        failures.append("construction does not match plan slot")

    plan_bindings = slot.bindings.values() if slot is not None else ()
    fact_references_valid = not (
        (set(plan_bindings) | {item.fact_id for item in candidate.term_uses})
        - facts.all_fact_ids
    )
    if not fact_references_valid:
        failures.append("fact reference is not present in bound scene facts")

    term_references_valid = all(item.term_id in by_term for item in candidate.term_uses)
    if not term_references_valid:
        failures.append("term reference is not in approved vocabulary")
    terms_with_matching_fact = all(
        item.term_id not in by_term or by_term[item.term_id].fact_id == item.fact_id
        for item in candidate.term_uses
    )
    if not terms_with_matching_fact:
        failures.append("term use fact does not match approved term")
        term_references_valid = False

    term_surfaces_are_reviewed = all(
        item.term_id not in by_term or item.surface in by_term[item.term_id].forms
        for item in candidate.term_uses
    )
    if not term_surfaces_are_reviewed:
        failures.append("term surface is not a reviewed form")
    term_surfaces_present = all(item.surface in candidate.text for item in candidate.term_uses)
    if not term_surfaces_present:
        failures.append("term surface is missing from candidate text")

    slot_labels = set(slot.required_labels) if slot is not None else set()
    labels_match = (
        set(candidate.label_uses) <= slot_labels
        and set(candidate.label_uses) <= set(by_label)
    )
    if not labels_match:
        failures.append("label use is not allowed by the plan slot and pack")
    label_texts_present = all(
        label_id not in by_label or by_label[label_id].text in candidate.text
        for label_id in candidate.label_uses
    )
    if not label_texts_present:
        failures.append("pack label text is missing from candidate text")

    chunks_reconstruct = join_chunks(candidate.chunks, pack.language.word_separator) == (
        candidate.text
    )
    if not chunks_reconstruct:
        failures.append("chunks do not reconstruct candidate text")
    text_is_nfc = (
        normalize("NFC", candidate.text) == candidate.text
        and all(normalize("NFC", chunk.text) == chunk.text for chunk in candidate.chunks)
        and all(normalize("NFC", item.surface) == item.surface for item in candidate.term_uses)
    )
    if not text_is_nfc:
        failures.append("candidate text, chunk, or term surface is not NFC")

    return DeterministicReport(
        unknown_slot=unknown_slot,
        construction_matches_slot=construction_matches,
        fact_references_valid=fact_references_valid,
        term_references_valid=term_references_valid,
        term_surfaces_are_reviewed=term_surfaces_are_reviewed,
        term_surfaces_present=term_surfaces_present,
        labels_match_slot_and_pack=labels_match,
        label_texts_present=label_texts_present,
        chunks_reconstruct=chunks_reconstruct,
        text_is_nfc=text_is_nfc,
        failures=failures,
    )


def assess(candidate: CandidateSentence, pack: LanguagePack) -> LinguisticAssessment:
    construction = next(
        (item for item in pack.constructions
         if item.construction_id == candidate.construction_id),
        None,
    )
    if construction is not None:
        matched = [
            example
            for example in construction.examples
            if candidate.text in {example.sentence, *example.accepted_alternatives}
        ]
        if any(example.provenance.review_status == "humanReviewed" for example in matched):
            return LinguisticAssessment(status="reviewedForm", passed=True)
        if matched:
            return LinguisticAssessment(status="unreviewedExample", passed=None)

    validator = _VALIDATORS.get((pack.language.code, candidate.construction_id))
    if validator is None:
        return LinguisticAssessment(status="notAssessed", passed=None)
    result = validator.validate(candidate, pack)
    return LinguisticAssessment(
        status="languageValidator",
        validator_id=validator.validator_id,
        passed=result.passed,
        messages=result.messages,
    )


def approve(
    candidates: Sequence[CandidateSentence],
    plan: LessonPlan,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    pack: LanguagePack,
    allow_unassessed: bool = False,
) -> ApprovalResult:
    approved = []
    failures = []
    for candidate in candidates:
        deterministic = check_deterministic(candidate, plan, facts, vocabulary, pack)
        assessment = assess(candidate, pack)
        reasons = list(deterministic.failures)
        allowed_status = assessment.status in {
            "reviewedForm", "humanApproved",
        } or (assessment.status == "languageValidator" and assessment.passed is True)
        if allow_unassessed and assessment.status in {"notAssessed", "unreviewedExample"}:
            allowed_status = True
        if not allowed_status:
            reasons.extend(assessment.messages or [f"assessment status is {assessment.status}"])
        if deterministic.passed and allowed_status:
            approved.append(
                ApprovedSentence(
                    candidate=candidate,
                    assessment=assessment,
                    deterministic_report=deterministic,
                    provenance=Provenance(
                        source=f"candidate origin: {candidate.origin}",
                        review_status="generated" if candidate.origin == "model" else "unreviewed",
                    ),
                    word_separator=pack.language.word_separator,
                )
            )
        else:
            failures.append(
                CandidateFailure(
                    candidate=candidate,
                    assessment=assessment,
                    deterministic_report=deterministic,
                    reasons=reasons,
                )
            )
    return ApprovalResult(approved=approved, failures=failures)
