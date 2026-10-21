"""Routed JSON generation and advisory assessment for local language-pack runs."""

# ruff: noqa: E501

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import Field

from app.ai.contracts.schema import build_strict_json_schema
from app.ai.contracts.text import TextModelConfig, TextModelRequest
from app.ai.routing.router import as_routed
from app.schemas.base import ApiModel, NonEmptyText

from .capabilities import LessonPlan
from .generation import (
    ApprovedVocabulary,
    BoundSceneFacts,
    CandidateSentence,
    LinguisticAssessment,
    RomanizedSpan,
    infer_term_uses,
    written_as_phrase,
)
from .loader import guidance_for_slot
from .schema import GuidanceBundle, LanguagePack

logger = logging.getLogger(__name__)

GENERATOR_VERSION = "lp-generator.v6"
ASSESSOR_VERSION = "lp-assessor.v1"

GENERATOR_SYSTEM_PROMPT = """You write sentences for one language-learning lesson. The user message is JSON with: language (code, locale, script, register,
variety), instruction_language, specs (each with slot_id, spec_id, construction_id, use, form, truth, required roles bound to
approved vocabulary forms, and required fixed labels), guidance (mandatory construction guidance, correct examples and incorrect examples
with corrections), and optionally repair (previous failures with exact reasons).
Rules:
- Write exactly one candidate for every spec, in the target language and register given. Vocabulary is meaning-anchored
  reference data, not an exhaustive dictionary. You may propose necessary grammatical forms and natural wording.
  Preserve fixed labels. Supply realizations (term_id, surface) when a bound term uses a new form, including agreement.
  Realizations are unreviewed claims; do not change the meaning or object instance attached to an ID.
  For each spec, use only its realization_terms IDs. Do not use fact IDs, example IDs or vocabulary
  IDs from other specs. Omit realizations when reference forms already express the sentence.
- State exactly the bound facts. When truth is false, state the counterfactual binding exactly as given; never add facts.
- A wrongExistence option denies the presence of its counterfactual object, while retaining the other bound facts.
  A wrongAttribute option replaces only the counterfactual detail or relation. A fact3 sentence adds another scene fact.
- Follow the construction guidance and the correct examples' structure. Do not copy an example unless its bindings match.
- Write each spec with form "sentence" as one complete sentence or question exactly as the learner should see it
  (capitalisation, spacing and punctuation included). Write each spec with form "phrase" (a vocabulary name, a position,
  a number with a noun) as only those words, exactly as on a vocabulary card or answer choice: no verb, no frame such as
  "this is" or "there is", and no final punctuation. Do not split either into tiles; the app derives tiles itself.
- translation is the meaning in the instruction language.
- If language.romanizationRequired is true, supply aligned romanization spans for every new sentence;
  each span contains native text and its Latin spelling. Concatenating native spans must reproduce text
  exactly, including spaces and punctuation. Otherwise romanization may be empty. Native text is canonical.
  Align each native word and punctuation mark separately, with spaces attached to the next native word;
  for scripts without word spaces use natural pedagogical words, preserving every native character.
  Also supply support_romanizations for all approved vocabulary forms and fixed learner-facing labels,
  so distractor words and preparation cards can display Latin spelling. These do not change native text.
- When repair is present, fix every listed reason for that spec and change nothing else that was not listed.
Return only JSON matching the schema."""

ASSESSOR_SYSTEM_PROMPT = """You review candidate sentences for a language-learning lesson. The user message is JSON with: language, register, the spec
(construction, bound facts, truth, roles and approved forms, fixed labels), the construction guidance and examples, and the
candidate text. Judge only this candidate:
- meaning_matches: it states exactly the bound facts (or the counterfactual when truth is false), nothing more or less.
- grammatical: it is a well-formed sentence of the target language and variety (agreement, word order, verb choice, punctuation).
- register_ok: it fits the given register.
- language_ok: every word is in the target language (fixed labels and approved forms count as target language).
List each problem in issues with a short reason. If unsure, set the field to false and say why. Return only JSON matching the
schema. Your judgement is advisory and will be reported as model assessment, not as verified correctness."""


class CandidateOutput(ApiModel):
    slot_id: NonEmptyText
    spec_id: NonEmptyText
    text: NonEmptyText
    translation: NonEmptyText
    romanization: list[RomanizedSpan] = Field(default_factory=list)
    realizations: list[TermRealization] = Field(default_factory=list)


class TermRealization(ApiModel):
    term_id: NonEmptyText
    surface: NonEmptyText


def _realization_terms(spec, vocabulary):
    by_id = {term.term_id: term for term in vocabulary.terms}
    by_fact = {term.fact_id: term for term in vocabulary.terms}
    roles = {
        role: by_fact[fact] for role, fact in spec.bindings.items()
        if role != "shown" and fact in by_fact
    }
    for role, term_id in spec.counterfactual.items():
        if term_id in by_id:
            roles[role] = by_id[term_id]
    if spec.use == "followup" and spec.construction_id == "describe-attribute":
        roles = {role: term for role, term in roles.items() if role in {"object", "subject"}}
    return roles


class CandidateResponse(ApiModel):
    candidates: list[CandidateOutput]
    support_romanizations: list[RomanizedSpan] = Field(default_factory=list)


class AssessorOutput(ApiModel):
    meaning_matches: bool
    grammatical: bool
    register_ok: bool
    language_ok: bool
    issues: list[NonEmptyText] = Field(default_factory=list)


class ModelSource:
    source_id = GENERATOR_VERSION

    def __init__(
        self, client: Any, config: TextModelConfig, *, mode: str = "model", propose: bool = True,
        language_context=None,
    ) -> None:
        self.client = as_routed(client, config, kind="text")
        self.mode = mode
        self.last_route = None
        self.propose = propose
        self.language_context = language_context

    def prepare(self, pack, level, facts, vocabulary):
        from .proposals import (
            PROPOSAL_PROMPT,
            PROPOSAL_VERSION,
            VocabularyProposals,
            apply_proposals,
        )

        self.original_vocabulary = vocabulary
        self.proposals = self._call(PROPOSAL_PROMPT, {
            "language": pack.language.model_dump(mode="json"),
            "register": pack.language_register.model_dump(mode="json"),
            "level": level, "facts": facts.model_dump(mode="json"),
            "session_vocabulary": vocabulary.model_dump(mode="json"),
            "guidance": [c.model_dump(mode="json") for c in pack.constructions],
        }, VocabularyProposals, "language_vocabulary_proposals", PROPOSAL_VERSION)
        return apply_proposals(vocabulary, facts, self.proposals)

    def review_content(self, pack, facts, plan, vocabulary, candidates, task=None):
        """Model content review of what this lesson uses.

        Only the lesson's constructions, words and proposals are sent: a reviewer given a
        whole pack reports uncertainty about it. Uncertainty with every criterion passed
        is not something a sentence repair can fix, so it is asked once more.
        """
        from .proposals import REVIEW_PROMPT, REVIEW_VERSION, ContentReview

        used = _lesson_scope(plan, vocabulary)
        payload = {
            "language": pack.language.model_dump(mode="json"),
            "register": pack.language_register.model_dump(mode="json"),
            "facts": facts.model_dump(mode="json"), "plan": plan.model_dump(mode="json"),
            "original_session_vocabulary": _terms_json(self.original_vocabulary, used),
            "proposals": _proposals_json(self.proposals, used),
            "candidate_vocabulary": _terms_json(vocabulary, used),
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "guidance": [
                c.model_dump(mode="json") for c in pack.constructions
                if c.construction_id in used["constructions"]
            ],
            "rendered_task": task.model_dump(mode="json") if task else None,
        }
        review = self._call(
            REVIEW_PROMPT, payload, ContentReview, "language_content_review", REVIEW_VERSION,
        )
        if review.only_uncertain:
            logger.warning("content review uncertain with every criterion met; asking again")
            review = self._call(
                REVIEW_PROMPT, payload, ContentReview, "language_content_review",
                REVIEW_VERSION,
            )
        return LinguisticAssessment(
            status="modelAssessed", validator_id=REVIEW_VERSION,
            passed=not review.failures, messages=review.failures,
        )

    def _call(self, system_prompt: str, payload: dict, model, name: str, version: str):
        if self.language_context is not None:
            payload = {**payload, "language_context": self.language_context.display.model_dump(
                mode="json",
            )}
        request = TextModelRequest(
            system_prompt=system_prompt,
            user_content=json.dumps(payload, ensure_ascii=False),
            json_schema_name=name,
            json_schema=build_strict_json_schema(model),
            prompt_version=version,
        )
        response = self.client.generate(request)
        self.last_route = response.route
        return model.model_validate_json(response.output_text)

    def generate(
        self,
        plan: LessonPlan,
        facts: BoundSceneFacts,
        vocabulary: ApprovedVocabulary,
        guidance: GuidanceBundle,
        pack: LanguagePack,
        repair: dict[str, list[str]] | None = None,
    ) -> list[CandidateSentence]:
        payload = {
            "language": pack.language.model_dump(mode="json"),
            "register": pack.language_register.model_dump(mode="json"),
            "variety": pack.variety.model_dump(mode="json"),
            "instruction_language": pack.instruction_language,
            "specs": [],
            "facts": facts.model_dump(mode="json", by_alias=False),
            ("candidate_vocabulary" if self.propose else "approved_vocabulary"):
                vocabulary.model_dump(mode="json"),
            "guidance": guidance.model_dump(mode="json"),
        }
        slot_guidance = []
        mission_key = (plan.mission_id, plan.practice_level, plan.content_version)
        for slot in plan.slots:
            for spec in slot.specs:
                scoped_guidance = guidance_for_slot(
                    pack, mission_key, slot.purpose, spec.construction_id
                )
                construction = next(
                    (item for item in pack.constructions
                     if item.construction_id == spec.construction_id),
                    None,
                )
                spec_data = {
                    "slot_id": slot.slot_id,
                    **spec.model_dump(mode="json", by_alias=False),
                    "form": "phrase" if written_as_phrase(spec.use, construction)
                    else "sentence",
                }
                if self.propose:
                    spec_data["realization_terms"] = [
                        {"role": role, "term_id": term.term_id, "meaning": term.source_text}
                        for role, term in _realization_terms(spec, vocabulary).items()
                    ]
                payload["specs"].append(spec_data)
                slot_guidance.append(
                    {
                        "slot_id": slot.slot_id,
                        "spec_id": spec.spec_id,
                        **scoped_guidance.model_dump(mode="json", by_alias=False),
                    }
                )
        payload["guidance"] = slot_guidance
        if repair:
            payload["repair"] = repair
        result = self._call(
            GENERATOR_SYSTEM_PROMPT,
            payload,
            CandidateResponse,
            "language_pack_candidates_v1",
            GENERATOR_VERSION,
        )
        specs = {(slot.slot_id, spec.spec_id): spec for slot in plan.slots for spec in slot.specs}
        returned = [(item.slot_id, item.spec_id) for item in result.candidates]
        if len(returned) != len(set(returned)) or set(returned) != set(specs):
            raise ValueError("model must return exactly one candidate for every planned spec")
        terms_by_id = {}
        for term in vocabulary.terms:
            terms_by_id[term.term_id] = term
        candidates = []
        for item in result.candidates:
            spec = specs[(item.slot_id, item.spec_id)]
            role_by_fact = {
                term.fact_id: role for role, term in _realization_terms(spec, vocabulary).items()
            }
            preferred_facts = set(role_by_fact)
            term_uses = [
                use.model_copy(update={"role": role_by_fact.get(use.fact_id)})
                for use in infer_term_uses(
                    item.text, vocabulary, preferred_fact_ids=preferred_facts
                )
            ]
            if item.realizations and not self.propose:
                raise ValueError("new realization claims require the assessed proposal workflow")
            from .generation import TermUse

            realization_issues = []
            allowed_ids = sorted(term.term_id for term in _realization_terms(spec, vocabulary).values())
            for realization in item.realizations:
                term = terms_by_id.get(realization.term_id)
                if term is None or term.fact_id not in preferred_facts:
                    realization_issues.append(
                        f"Invalid realization term_id={realization.term_id!r}, "
                        f"surface={realization.surface!r} for {item.slot_id}/{item.spec_id}. "
                        f"Use only this spec's term IDs: {allowed_ids!r}, or omit "
                        "the claim if reference forms already express the sentence. "
                        "Keep the planned meaning and object binding unchanged."
                    )
                    continue
                term_uses.append(TermUse(
                    term_id=term.term_id, fact_id=term.fact_id,
                    surface=realization.surface, role=role_by_fact.get(term.fact_id),
                ))
            candidates.append(
                CandidateSentence(
                    slot_id=item.slot_id,
                    spec_id=item.spec_id,
                    spec_use=spec.use,
                    truth=spec.truth,
                    construction_id=spec.construction_id,
                    text=item.text,
                    translation=item.translation,
                    romanization=item.romanization,
                    support_romanizations=result.support_romanizations,
                    term_uses=term_uses,
                    label_uses=spec.labels,
                    origin="model",
                    proposed_realizations=self.propose,
                    validation_issues=realization_issues,
                )
            )
        return candidates

    def assess(
        self,
        candidate: CandidateSentence,
        spec: dict,
        guidance: GuidanceBundle,
        pack: LanguagePack,
    ) -> LinguisticAssessment:
        output = self._call(
            ASSESSOR_SYSTEM_PROMPT,
            {
                "language": pack.language.model_dump(mode="json"),
                "register": pack.language_register.model_dump(mode="json"),
                "spec": spec,
                "guidance": guidance.model_dump(mode="json"),
                "candidate": candidate.text,
            },
            AssessorOutput,
            "language_pack_assessment_v1",
            ASSESSOR_VERSION,
        )
        passed = all(
            (
                output.meaning_matches,
                output.grammatical,
                output.register_ok,
                output.language_ok,
            )
        )
        return LinguisticAssessment(
            status="modelAssessed",
            validator_id=ASSESSOR_VERSION,
            passed=passed,
            messages=list(output.issues),
        )


def _lesson_scope(plan, vocabulary):
    """Constructions, facts and terms the planned specs use."""
    facts = {fact for slot in plan.slots for spec in slot.specs
             for fact in spec.bindings.values()}
    term_ids = {term_id for slot in plan.slots for spec in slot.specs
                for term_id in spec.counterfactual.values()}
    term_ids |= {term.term_id for term in vocabulary.terms if term.fact_id in facts}
    term_facts = {term.fact_id for term in vocabulary.terms if term.term_id in term_ids}
    # Model alternatives anchored to a bound fact are the lesson's possible distractors.
    term_ids |= {term.term_id for term in vocabulary.terms
                 if term.linguistic.get("contrast-for") in facts}
    return {
        "constructions": {spec.construction_id for slot in plan.slots for spec in slot.specs},
        "facts": facts | term_facts,
        "terms": term_ids,
    }


def _terms_json(vocabulary, used):
    return {"terms": [term.model_dump(mode="json") for term in vocabulary.terms
                      if term.term_id in used["terms"] or term.fact_id in used["facts"]]}


def _proposals_json(proposals, used):
    if proposals is None:
        return None
    return {
        "forms": [item.model_dump(mode="json") for item in proposals.forms
                  if item.term_id in used["terms"]],
        "distractors": [item.model_dump(mode="json") for item in proposals.distractors
                        if item.for_fact_id in used["facts"]],
    }
