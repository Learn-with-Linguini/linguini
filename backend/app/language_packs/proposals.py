"""Unreviewed model proposals anchored to session meanings, never new scene facts."""

from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel, NonEmptyText

from .generation import ApprovedTerm, ApprovedVocabulary

PROPOSAL_VERSION = "language-proposals.v2"
REVIEW_VERSION = "language-content-review.v1"

PROPOSAL_PROMPT = """Supply candidate grammatical forms and distractors for planned M01
lesson. Packs are guidance and optional reference vocabulary, not exhaustive dictionaries.
Preserve each session term's meaning and ID. Supply necessary noun phrases/articles and adjective
agreement forms as a list of key/text entries (bare, definite, indefinite, article_definite,
article_indefinite, masculine/feminine/neuter for in-sentence agreement, and predicative when a
detail named on its own differs from those forms, e.g. German rot beside rote/roter/rotes).
These are proposals, not reviewed forms. Do not change scene facts.
For every attribute/relation needing choices, propose two distinct alternatives, each tied to its
for_fact_id, with meaning in the instruction language, native text and required agreement forms.
Use natural words outside reference lists when appropriate to the level/register. Alternate nouns
may be absent from the photo, but are answer alternatives, never asserted scene facts. Detector
omission is not evidence of absence. Respect the existing exercise: semantically wrong options
must be grammatical, plausible, unambiguous and not synonyms of the correct answer. Avoid subtle
colour distinctions, overlapping attributes and relations that could simultaneously hold. Do not
use grammatical mistakes as clues in semantic MCQs. Only use fact IDs supplied in session data.
Return JSON matching the schema. Reference examples are guidance, not a required word list."""

REVIEW_PROMPT = """Assess candidate lesson content against original session vocabulary,
confirmed scene facts, planned bindings, level/register and construction guidance. Neither supplied
candidate forms nor a generator's claims are approved or human-reviewed. Check every sentence,
form, translation and proposed distractor. New words/forms outside pack lists are allowed if they
preserve assessed meanings. Verify realizations against original meanings, including object IDs.
Counterfactual options are alternatives to the bound target, never newly asserted scene facts.
Omission by a detector never proves absence. A false option may deny a confirmed-present object,
but do not accept unsupported absence as a correct fact. For a rendered lesson, inspect every
option against its question and answer key; exactly the intended answer(s) must be defensible.
Check grammatical suitability, level/register, distinct meaning, ambiguity and exercise policy.
Semantic distractors must be grammatical; grammar errors are allowed only in an explicitly
designated grammar-error exercise. Treat synonyms, equivalent descriptions, overlapping colours,
coexisting relations and indistinguishable objects as ambiguous when they yield another correct
answer. Also assess supports and feedback. Mark uncertainty explicitly: if uncertain, set certain
false and explain. Model assessment is fallible and is not fluent human review or release proof.
Return all schema fields, with issues explaining each failed or uncertain criterion."""


class ProposedForm(ApiModel):
    key: NonEmptyText
    text: NonEmptyText


class FormProposal(ApiModel):
    term_id: NonEmptyText
    forms: list[ProposedForm]
    agreement: str | None = None
    position: Literal["before", "after"] | None = None


class DistractorProposal(ApiModel):
    for_fact_id: NonEmptyText
    meaning: NonEmptyText
    text: NonEmptyText
    forms: list[ProposedForm] = Field(default_factory=list)


class VocabularyProposals(ApiModel):
    forms: list[FormProposal]
    distractors: list[DistractorProposal]


class ContentReview(ApiModel):
    meaning_matches: bool
    grammatical: bool
    level_register_ok: bool
    distractors_suitable: bool
    distinct: bool
    unambiguous: bool
    scene_claims_supported: bool
    certain: bool
    issues: list[NonEmptyText]

    @property
    def failures(self):
        fields = (
            "meaning_matches", "grammatical", "level_register_ok", "distractors_suitable",
            "distinct", "unambiguous", "scene_claims_supported", "certain",
        )
        failed = [f"model assessment: {key}=false" for key in fields if not getattr(self, key)]
        return [*failed, *self.issues] if failed or self.issues else []


def apply_proposals(original, facts, proposals):
    """Validate identities mechanically; linguistic acceptance requires content review later."""
    terms = {term.term_id: term for term in original.terms}
    seen = set()
    for proposal in proposals.forms:
        if proposal.term_id not in terms or proposal.term_id in seen:
            raise ValueError("form proposal has unknown or duplicate session term ID")
        seen.add(proposal.term_id)
        term = terms[proposal.term_id]
        forms = {**term.forms_by_key, **_forms(proposal.forms)}
        terms[term.term_id] = ApprovedTerm.model_validate({
            **term.model_dump(by_alias=False), "forms_by_key": forms,
            "forms": list(dict.fromkeys([*term.forms, *forms.values()])),
            "agreement": proposal.agreement or term.agreement,
            "position": proposal.position or term.position,
            "provenance": "modelProposal",
        })
    by_fact = {term.fact_id: term for term in original.terms}
    attributes = {attr.fact_id: attr for attr in facts.scene_facts.attributes}
    relations = {rel.fact_id: rel for rel in facts.scene_facts.relations}
    objects = {obj.fact_id for obj in facts.scene_facts.objects}
    distinct = set()
    for index, proposal in enumerate(proposals.distractors):
        anchor = by_fact.get(proposal.for_fact_id)
        if anchor is None or anchor.fact_id not in attributes.keys() | relations.keys() | objects:
            raise ValueError("distractor must reference a confirmed object, attribute or relation")
        keys = {(anchor.fact_id, "text", proposal.text.casefold()),
                (anchor.fact_id, "meaning", proposal.meaning.casefold())}
        if keys & distinct or proposal.meaning.casefold() == anchor.source_text.casefold():
            raise ValueError("distractor duplicates the target meaning or another proposal")
        if proposal.text.casefold() in {form.casefold() for form in anchor.forms}:
            raise ValueError("distractor duplicates a target surface form")
        distinct.update(keys)
        attribute = attributes.get(anchor.fact_id)
        metadata = {"contrast-for": anchor.fact_id}
        if attribute:
            metadata["attribute-kind"] = attribute.kind
        elif anchor.fact_id in relations:
            metadata["relation-kind"] = proposal.meaning
        else:
            metadata["alternative-kind"] = "noun"
        forms = {"default": proposal.text, **_forms(proposal.forms)}
        tid = f"model-contrast-{index}"
        terms[tid] = ApprovedTerm(
            term_id=tid, fact_id=f"alternative:{index}", source_text=proposal.meaning,
            target_text=proposal.text, forms=list(dict.fromkeys(forms.values())),
            forms_by_key=forms, part_of_speech=anchor.part_of_speech,
            provenance="modelProposal", linguistic=metadata,
        )
    return ApprovedVocabulary(terms=list(terms.values()))


def _forms(entries):
    if len({entry.key for entry in entries}) != len(entries):
        raise ValueError("proposed grammatical form keys must be unique")
    return {entry.key: entry.text for entry in entries}
