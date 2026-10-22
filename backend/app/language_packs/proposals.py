"""Unreviewed model proposals anchored to session meanings, never new scene facts."""

import logging
from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel, NonEmptyText

from .generation import ApprovedTerm, ApprovedVocabulary

logger = logging.getLogger(__name__)

PROPOSAL_VERSION = "language-proposals.v6"
REVIEW_VERSION = "language-content-review.v4"

PROPOSAL_PROMPT = """Supply candidate grammatical forms and distractors for a planned
lesson. Packs are guidance and optional reference vocabulary, not exhaustive dictionaries.
Preserve each session term's meaning and ID. Supply necessary noun phrases/articles and adjective
agreement forms as a list of key/text entries (bare, definite, indefinite, article_definite,
article_indefinite, masculine/feminine/neuter for in-sentence agreement, predicative when a
detail named on its own differs from those forms, e.g. German rot beside rote/roter/rotes,
modifier when a detail takes another form before a noun, e.g. Korean 빨간 beside 빨간색, and
plural for a noun counted after a number above one when it differs from bare, e.g. Spanish
libros, German Äpfel; omit plural where the language does not mark it after numbers).
Number words and possessive words are pack data: never propose forms for them. Give at most
one forms entry per session term_id, with every form for that term in it, and use only term_ids
from the session.
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
candidate forms nor a generator's claims are approved or human-reviewed. Check every candidate
sentence and rendered option, and the forms, translations and distractors they use; ignore
proposals that no planned spec or rendered question uses. New words/forms outside pack lists are
allowed if they preserve assessed meanings. The English source meanings (sourceText) and object
IDs are authoritative; native session words are machine translations. Verify realizations against
those meanings. If a session word does not express its English meaning, say so in issues as the
cause (a translation error), rather than listing every criterion it affects. Romanization is
checked mechanically elsewhere; do not assess it.
Judge only the supplied candidates and, when present, the rendered task. Without a rendered
task, the distractors are the candidates that are options or have truth false; set
distractors_suitable, distinct and unambiguous true when those candidates meet the criteria.
Guidance, vocabulary and proposals are context: never fail or doubt a criterion because of
their size or because something is absent from them.
Counterfactual options are alternatives to the bound target, never newly asserted scene facts.
Deliberate lesson design is not an error: a yes/no question with truth false names something
other than the shown object, and its correct answer is no; a hidden-referent clue never names
its target, while other constructions in the same lesson do name objects; in ownership lessons
possessives follow the speaker (the learner says my for their own object, Linguini says your to
the learner) and role-play owners are pretend.
Omission by a detector never proves absence. A false option may deny a confirmed-present object,
but do not accept unsupported absence as a correct fact. For a rendered lesson, inspect every
option against its question and answer key; exactly the intended answer(s) must be defensible.
Check grammatical suitability, level/register, distinct meaning, ambiguity and exercise policy.
Semantic distractors must be grammatical; grammar errors are allowed only in an explicitly
designated grammar-error exercise. Treat synonyms, equivalent descriptions, overlapping colours,
coexisting relations and indistinguishable objects as ambiguous when they yield another correct
answer. Also assess supports and feedback. Set certain false only when you cannot judge a
specific sentence or option, and name it in issues. Model assessment is fallible and is not
fluent human review or release proof. Return all schema fields. issues lists only problems,
each naming the sentence or option and the failed criterion; leave it empty when everything
passes, and never use it for observations or praise."""


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
        failed = [f"model assessment: {key}=false" for key in _CRITERIA if not getattr(self, key)]
        # The criteria decide; issues only explain a failure (reviewers also write notes).
        return [*failed, *self.issues] if failed else []

    @property
    def only_uncertain(self) -> bool:
        """Every criterion passed, but the reviewer was not certain."""
        return not self.certain and all(
            getattr(self, key) for key in _CRITERIA if key != "certain"
        )


_CRITERIA = (
    "meaning_matches", "grammatical", "level_register_ok", "distractors_suitable",
    "distinct", "unambiguous", "scene_claims_supported", "certain",
)


def apply_proposals(original, facts, proposals):
    """Validate identities mechanically; linguistic acceptance requires content review later.

    Proposals are optional extra forms, so a sloppy entry is dropped rather than failing
    the lesson: entries for unknown term IDs are ignored, repeated entries for one term
    are merged, and invalid distractors are skipped. Later checks still require what a
    lesson needs (bound forms, enough alternatives).
    """
    terms = {term.term_id: term for term in original.terms}
    for proposal in _merged_forms(proposals.forms, terms):
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
            logger.warning("skipping a distractor for an unconfirmed fact")
            continue
        keys = {(anchor.fact_id, "text", proposal.text.casefold()),
                (anchor.fact_id, "meaning", proposal.meaning.casefold())}
        if keys & distinct or proposal.meaning.casefold() == anchor.source_text.casefold() or (
            proposal.text.casefold() in {form.casefold() for form in anchor.forms}
        ):
            logger.warning("skipping a distractor that repeats the target or another proposal")
            continue
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


def _merged_forms(proposals, terms):
    """One form proposal per known session term; the first text proposed for a key wins."""
    merged: dict[str, FormProposal] = {}
    for proposal in proposals:
        if proposal.term_id not in terms:
            logger.warning("ignoring proposed forms for an unknown session term")
            continue
        if getattr(terms[proposal.term_id], "provenance", None) == "packData":
            logger.info("ignoring proposed forms for reviewed pack words")
            continue
        previous = merged.get(proposal.term_id)
        if previous is None:
            merged[proposal.term_id] = proposal
            continue
        logger.warning("merging repeated proposed forms for one session term")
        merged[proposal.term_id] = previous.model_copy(update={
            "forms": [*previous.forms, *proposal.forms],
            "agreement": previous.agreement or proposal.agreement,
            "position": previous.position or proposal.position,
        })
    return list(merged.values())


def _forms(entries):
    """Proposed forms by key; a repeated key keeps its first text."""
    forms = {}
    for entry in entries:
        if forms.setdefault(entry.key, entry.text) != entry.text:
            logger.warning("ignoring a conflicting proposed form for key %s", entry.key)
    return forms
