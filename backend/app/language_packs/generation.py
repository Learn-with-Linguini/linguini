"""Typed, model-independent language-pack generation and assessment stages."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Literal, Protocol
from unicodedata import normalize
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.ai.features.learning_tasks.mission import fold, tokens
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
type VocabularyProvenance = Literal[
    "reviewedLexicon", "catalog", "sessionTranslation", "packData", "modelProposal",
]
type CandidateOrigin = Literal["model", "reviewedForm", "manual"]
type AdjectivePosition = Literal["before", "after"]
type AssessmentStatus = Literal[
    "notAssessed",
    "unreviewedExample",
    "reviewedForm",
    "languageValidator",
    "humanApproved",
    "modelAssessed",
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
    """Historical contract name for reference terms; provenance records review status.

    modelProposal entries are unreviewed candidates and require contextual assessment.
    Membership in this container never establishes linguistic correctness.
    """
    term_id: ContractId
    fact_id: NonEmptyText
    source_text: NonEmptyText
    target_text: NonEmptyText
    forms: list[NonEmptyText] = Field(min_length=1)
    forms_by_key: dict[NonEmptyText, NonEmptyText] = Field(default_factory=dict)
    part_of_speech: PartOfSpeech
    agreement: NonEmptyText | None = None
    position: AdjectivePosition | None = None
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
        if unknown := set(self.forms_by_key.values()) - set(self.forms):
            raise ValueError(f"forms_by_key values must appear in forms: {sorted(unknown)}")
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
    role: str | None = None


class RomanizedSpan(ApiModel):
    """A generated native span and its Latin spelling, including joining whitespace."""

    native: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1)]
    latin: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1)]


class CandidateSentence(ApiModel):
    slot_id: NonEmptyText
    spec_id: NonEmptyText | None = None
    spec_use: NonEmptyText | None = None
    truth: bool | None = None
    construction_id: ContractId
    text: NonEmptyText
    translation: NonEmptyText | None = None
    chunks: list[SentenceChunk] = Field(default_factory=list)
    term_uses: list[TermUse] = Field(default_factory=list)
    label_uses: list[ContractId] = Field(default_factory=list)
    origin: CandidateOrigin
    romanization: list[RomanizedSpan] = Field(default_factory=list)
    support_romanizations: list[RomanizedSpan] = Field(default_factory=list)
    # Unreviewed realization claims, checked semantically before sentence acceptance.
    proposed_realizations: bool = False
    # Parser diagnostics remain candidate failures so bounded repair can fix them.
    validation_issues: list[str] = Field(default_factory=list)

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
    matched_example_id: str | None = None
    matched_review_status: str | None = None


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
    failures = list(candidate.validation_issues)

    unknown_slot = slot is None
    if unknown_slot:
        failures.append("unknown slot")
    spec = None
    if slot is not None:
        spec = next(
            (item for item in slot.specs if item.spec_id == (candidate.spec_id or slot.slot_id)),
            None,
        )
        if spec is None and len(slot.specs) == 1:
            spec = slot.specs[0]
    construction_matches = (
        slot is not None
        and candidate.construction_id in slot.construction_ids
        and (spec is None or candidate.construction_id == spec.construction_id)
    )
    if not construction_matches:
        failures.append("construction does not match plan slot")

    construction = next(
        (item for item in pack.constructions if item.construction_id == candidate.construction_id),
        None,
    )
    expected_bindings = dict(spec.bindings) if spec is not None else {}
    counterfactual_ids = set()
    if spec is not None:
        for role, term_id in spec.counterfactual.items():
            term = by_term.get(term_id)
            if term is not None:
                expected_bindings[role] = term.fact_id
                counterfactual_ids.add(term.fact_id)
    fact_references_valid = not (
        set(expected_bindings.values()) - (facts.all_fact_ids | counterfactual_ids)
    )
    if not fact_references_valid:
        failures.append("fact reference is not present in bound scene facts")
    # ``target`` names an object a clue describes without naming it in the sentence.
    bound_object = (
        expected_bindings.get("object")
        or expected_bindings.get("subject")
        or expected_bindings.get("first")
        or expected_bindings.get("target")
    )
    bound_attribute = expected_bindings.get("attribute")
    if bound_attribute and "attribute" not in (spec.counterfactual if spec else {}):
        attribute = next(
            (a for a in facts.scene_facts.attributes if a.fact_id == bound_attribute), None
        )
        if attribute is None or attribute.object_fact_id != bound_object:
            failures.append("attribute binding belongs to another object instance")
    bound_relation = expected_bindings.get("relation")
    if bound_relation and "relation" not in (spec.counterfactual if spec else {}):
        relation = next(
            (r for r in facts.scene_facts.relations if r.fact_id == bound_relation), None
        )
        if relation is None or (
            relation.subject_fact_id != expected_bindings.get("subject", bound_object)
            or relation.reference_fact_id != expected_bindings.get("reference")
        ):
            failures.append("relation binding does not match its subject and reference instances")

    derived_uses = infer_term_uses(
        candidate.text,
        vocabulary,
        preferred_fact_ids={fact for role, fact in expected_bindings.items() if role != "shown"},
    )
    term_references_valid = all(
        item.term_id in by_term
        and by_term[item.term_id].fact_id == item.fact_id
        and (item.role not in expected_bindings or expected_bindings[item.role] == item.fact_id)
        for item in candidate.term_uses
    )
    if not term_references_valid:
        failures.append("candidate term claims do not match approved vocabulary")
    term_surfaces_are_reviewed = True
    term_surfaces_present = all(
        any(
            fold(use.surface) == fold(surface)
            for term in vocabulary.terms
            if term.term_id == use.term_id
            for surface in [*term.forms, *term.forms_by_key.values()]
        )
        for use in candidate.term_uses
    )
    term_surfaces_are_reviewed = not candidate.proposed_realizations and all(
        by_term[use.term_id].provenance in {"reviewedLexicon", "catalog"}
        for use in candidate.term_uses if use.term_id in by_term
    )
    if not term_surfaces_present and not candidate.proposed_realizations:
        failures.append("candidate term claim is not a reviewed form")
    if candidate.proposed_realizations:
        claimed = [
            use for use in candidate.term_uses
            if use.term_id in by_term and use.fact_id == by_term[use.term_id].fact_id
            and fold(use.surface) in fold(candidate.text)
        ]
        if len(claimed) != len(candidate.term_uses):
            failures.append("proposed realization must occur in the candidate sentence")
        # Identity is anchored mechanically; semantic equivalence is model-assessed,
        # never established by a realization claim or membership in a word list.
        derived_uses = [*derived_uses, *claimed]

    if spec is not None and construction is not None:
        expected_roles = construction.roles
        if spec.use == "followup":
            # A detail question names its subject; the answer's bound detail is
            # context, and must not be leaked in the question.
            expected_roles = {
                role: pos for role, pos in expected_roles.items() if role in {"object", "subject"}
            }
        if candidate.construction_id == "yes-no-identification":
            expected_roles = {"object": "noun"}
        allowed_fact_ids = set(expected_bindings.values())
        for role, fact_id_value in expected_bindings.items():
            expected_pos = expected_roles.get(role)
            if expected_pos is None:
                continue
            realized = [
                use
                for use in derived_uses
                if use.fact_id == fact_id_value
                and str(
                    getattr(
                        by_term[use.term_id].part_of_speech,
                        "value",
                        by_term[use.term_id].part_of_speech,
                    )
                )
                == expected_pos
            ]
            if not realized:
                found = [
                    use
                    for use in derived_uses
                    if str(
                        getattr(
                            by_term[use.term_id].part_of_speech,
                            "value",
                            by_term[use.term_id].part_of_speech,
                        )
                    )
                    == expected_pos
                ]
                found_facts = sorted({use.fact_id for use in found})
                failures.append(
                    f"role {role!r} expects {fact_id_value!r}; found facts {found_facts or 'none'}"
                )
        expected_pos = set(expected_roles.values())
        unbound = [
            use
            for use in derived_uses
            if use.fact_id not in allowed_fact_ids
            and str(
                getattr(
                    by_term[use.term_id].part_of_speech,
                    "value",
                    by_term[use.term_id].part_of_speech,
                )
            )
            in expected_pos
        ]
        if unbound:
            failures.append(
                "sentence contains unbound approved facts: "
                + ", ".join(sorted({use.fact_id for use in unbound}))
            )

    if spec is not None and candidate.construction_id == "yes-no-identification":
        if spec.use in {"question", "prompt"}:
            object_fact = spec.bindings.get("object")
            shown_fact = spec.bindings.get("shown")
            if shown_fact is not None and spec.truth != (object_fact == shown_fact):
                failures.append("yes/no question truth does not match asked and shown objects")
        elif spec.use in {"answer", "option"}:
            expected_label = "yes" if spec.truth else "no"
            if expected_label not in spec.labels:
                failures.append(f"answer must use the {expected_label!r} label")
            shown_fact = spec.bindings.get("shown")
            if (
                spec.use == "answer"
                and shown_fact is not None
                and spec.bindings.get("object") != shown_fact
            ):
                failures.append("yes/no answer must name the shown object")

    slot_sentence_labels = set(slot.sentence_labels) if slot is not None else set()
    expected_labels = set(spec.labels) if spec is not None else set()
    found_labels = {
        semantic
        for semantic, label in by_label.items()
        if semantic in slot_sentence_labels
        and label.usage == "sentence"
        and _fixed_label_occurs(candidate.text, label.text, semantic)
    }
    labels_match = (
        expected_labels <= found_labels
        and found_labels <= slot_sentence_labels
        and found_labels <= set(by_label)
        and set(candidate.label_uses) <= slot_sentence_labels
    )
    if not labels_match:
        failures.append("sentence labels do not match the spec and slot")
    label_texts_present = all(
        semantic in by_label
        and _fixed_label_occurs(candidate.text, by_label[semantic].text, semantic)
        for semantic in expected_labels
    )
    if not label_texts_present:
        failures.append("required fixed label text is missing from candidate text")

    chunks_reconstruct = (
        not candidate.chunks
        or join_chunks(candidate.chunks, pack.language.word_separator) == candidate.text
    )
    if not chunks_reconstruct:
        failures.append("chunks do not reconstruct candidate text")
    if not candidate.chunks:
        try:
            derive_chunks(candidate, pack.language.word_separator)
        except ValueError:
            chunks_reconstruct = False
            failures.append("sentence cannot be reconstructed by derived chunks")
    text_is_nfc = (
        normalize("NFC", candidate.text) == candidate.text
        and all(normalize("NFC", chunk.text) == chunk.text for chunk in candidate.chunks)
        and all(normalize("NFC", item.surface) == item.surface for item in derived_uses)
    )
    if not text_is_nfc:
        failures.append("candidate text, chunk, or term surface is not NFC")
    if candidate.romanization or pack.language.romanization_required:
        from unicodedata import name

        if (
            not candidate.romanization
            or "".join(span.native for span in candidate.romanization) != candidate.text
        ):
            failures.append("romanization must align exactly with the complete native sentence")
        for span in [*candidate.romanization, *candidate.support_romanizations]:
            if any(char.isalpha() and "LATIN" not in name(char, "") for char in span.latin):
                failures.append("romanization spelling must use Latin letters")
            if normalize("NFC", span.latin) != span.latin:
                failures.append("romanization must be NFC")

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


def infer_term_uses(
    text: str,
    vocabulary: ApprovedVocabulary,
    *,
    preferred_fact_ids: set[str] | None = None,
) -> list[TermUse]:
    sentence_tokens = [fold(token).strip("¿¡«»") for token in tokens(text)]
    matches: dict[int, list[tuple[int, ApprovedTerm, str]]] = {}
    for term in vocabulary.terms:
        surfaces = dict.fromkeys(
            [
                *term.forms,
                *(
                    value
                    for key, value in term.forms_by_key.items()
                    if not key.startswith("article")
                ),
            ]
        )
        articles = {v for k, v in term.forms_by_key.items() if k.startswith("article")}
        for surface in surfaces:
            surface_tokens = [fold(token).strip("¿¡«»") for token in tokens(surface)]
            surface_tokens = [token for token in surface_tokens if token]
            if not surface_tokens or (surface in articles):
                continue
            width = len(surface_tokens)
            for start in range(len(sentence_tokens) - width + 1):
                if sentence_tokens[start : start + width] == surface_tokens:
                    matches.setdefault(start, []).append((width, term, surface))
    selected: dict[tuple[str, int], tuple[int, ApprovedTerm, str]] = {}
    occupied_until = 0
    used_facts = set()
    for start, options in sorted(matches.items()):
        if start < occupied_until:
            continue
        longest = max(item[0] for item in options)
        best = [item for item in options if item[0] == longest]
        preferred = [
            item for item in best if preferred_fact_ids and item[1].fact_id in preferred_fact_ids
        ]
        unused = [item for item in preferred if item[1].fact_id not in used_facts]
        width, term, surface = sorted(
            unused or preferred or best,
            key=lambda item: (item[1].term_id, item[2]),
        )[0]
        selected[(term.term_id, start)] = (width, term, surface)
        occupied_until = start + width
        used_facts.add(term.fact_id)
    by_fact: dict[str, tuple[int, ApprovedTerm, str]] = {}
    for (_term_id, _start), option in selected.items():
        width, term, surface = option
        current = by_fact.get(term.fact_id)
        if current is None or width > current[0]:
            by_fact[term.fact_id] = (width, term, surface)
    return [
        TermUse(term_id=term.term_id, surface=surface, fact_id=term.fact_id)
        for _width, term, surface in by_fact.values()
    ]


def _fixed_label_occurs(text: str, label: str, semantic: str) -> bool:
    normalized_text = fold(text)
    normalized_label = fold(label).strip(".,!?;:")
    if semantic in {"yes", "no"}:
        first_word = normalized_text.split(maxsplit=1)[0].strip(".,!?;:") if normalized_text else ""
        return first_word == normalized_label
    return normalized_label in normalized_text


def derive_chunks(
    candidate: CandidateSentence,
    word_separator: WordSeparator,
    *,
    phrase_chunks: bool = False,
    phrase_boundaries: Sequence[str] = (),
) -> CandidateSentence:
    # Keep punctuation, combining marks and script characters exactly as generated.
    # Phrase tiles group sentences, independently of a language's conjunctions.
    pattern = r"[^\s.,!?;:'’]+['’]?|[.,!?;:]"
    matches = list(re.finditer(pattern, candidate.text))
    if phrase_chunks:
        grouped, current = [], []
        boundaries = {value.casefold() for value in phrase_boundaries}
        for match in matches:
            if (
                match.group() in {".", ",", "?", "!", ";", ":"}
                or match.group().casefold() in boundaries
            ):
                if current:
                    grouped.append((current[0].start(), current[-1].end()))
                    current = []
                grouped.append((match.start(), match.end()))
            else:
                current.append(match)
        if current:
            grouped.append((current[0].start(), current[-1].end()))
        spans = grouped
    else:
        spans = [(match.start(), match.end()) for match in matches]
    if candidate.romanization and not phrase_chunks:
        spans = []
        offset = 0
        for span in candidate.romanization:
            start = offset + len(span.native) - len(span.native.lstrip())
            stop = offset + len(span.native.rstrip())
            if stop > start:
                spans.append((start, stop))
            offset += len(span.native)
    sentence_chunks = []
    end = 0
    for start, stop in spans:
        gap = candidate.text[end:start]
        if gap not in {"", " "}:
            raise ValueError("sentence spacing cannot be represented by tiles")
        sentence_chunks.append(
            SentenceChunk(text=candidate.text[start:stop], join="space" if gap else "none")
        )
        end = stop
    if join_chunks(sentence_chunks, word_separator) != candidate.text:
        raise ValueError("derived chunks do not reconstruct candidate text")
    return candidate.model_copy(update={"chunks": sentence_chunks})


def assess(
    candidate: CandidateSentence,
    pack: LanguagePack,
    vocabulary: ApprovedVocabulary | None = None,
) -> LinguisticAssessment:
    matched_example = None
    construction = next(
        (item for item in pack.constructions if item.construction_id == candidate.construction_id),
        None,
    )
    if construction is not None:
        matched = [
            example
            for example in construction.examples
            if candidate.text in {example.sentence, *example.accepted_alternatives}
        ]
        reviewed = next(
            (example for example in matched if example.provenance.review_status == "humanReviewed"),
            None,
        )
        if reviewed is not None:
            return LinguisticAssessment(
                status="reviewedForm",
                passed=True,
                matched_example_id=reviewed.example_id,
                matched_review_status=reviewed.provenance.review_status,
            )
        matched_example = matched[0] if matched else None

    if vocabulary is not None:
        from .validators import select_validator

        validator = select_validator(pack.language.code, vocabulary, pack)
    else:
        validator = _VALIDATORS.get((pack.language.code, candidate.construction_id))
    if validator is None:
        return LinguisticAssessment(
            status="notAssessed",
            passed=None,
            matched_example_id=matched_example.example_id if matched_example else None,
            matched_review_status=(
                matched_example.provenance.review_status if matched_example else None
            ),
        )
    result = validator.validate(candidate, pack)
    if candidate.proposed_realizations:
        return LinguisticAssessment(
            status="notAssessed", validator_id=validator.validator_id,
            passed=False if not result.passed else None,
            messages=result.messages or [
                "Proposed language requires contextual content assessment.",
            ],
        )
    return LinguisticAssessment(
        status="languageValidator",
        validator_id=validator.validator_id,
        passed=result.passed,
        messages=result.messages,
        matched_example_id=matched_example.example_id if matched_example else None,
        matched_review_status=(
            matched_example.provenance.review_status if matched_example else None
        ),
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
        if candidate.proposed_realizations:
            reasons.append("Proposed language requires the contextual content-assessment pipeline")
        allowed_status = assessment.status in {
            "reviewedForm", "humanApproved",
        } or (assessment.status == "languageValidator" and assessment.passed is True)
        if allow_unassessed and assessment.status in {"notAssessed", "unreviewedExample"}:
            allowed_status = True
        if not allowed_status:
            reasons.extend(assessment.messages or [f"assessment status is {assessment.status}"])
        if deterministic.passed and allowed_status and not candidate.proposed_realizations:
            accepted_candidate = derive_chunks(
                candidate,
                pack.language.word_separator,
                phrase_chunks=str(plan.practice_level) == "A2",
            )
            approved.append(
                ApprovedSentence(
                    candidate=accepted_candidate,
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
