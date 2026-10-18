"""Routed JSON generation and advisory assessment for local language-pack runs."""

# ruff: noqa: E501

from __future__ import annotations

import json
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
    infer_term_uses,
)
from .loader import guidance_for_slot
from .schema import GuidanceBundle, LanguagePack

GENERATOR_VERSION = "lp-generator.v1"
ASSESSOR_VERSION = "lp-assessor.v1"

GENERATOR_SYSTEM_PROMPT = """You write sentences for one language-learning lesson. The user message is JSON with: language (code, locale, script, register,
variety), instruction_language, specs (each with slot_id, spec_id, construction_id, truth, required roles bound to approved
vocabulary forms, and required fixed labels), guidance (mandatory construction guidance, correct examples and incorrect examples
with corrections), and optionally repair (previous failures with exact reasons).
Rules:
- Write exactly one candidate for every spec, in the target language and register given. Use only the approved vocabulary forms
  and fixed label texts supplied; do not add other content words.
- State exactly the bound facts. When truth is false, state the counterfactual binding exactly as given; never add facts.
- Follow the construction guidance and the correct examples' structure. Do not copy an example unless its bindings match.
- Write each candidate as one complete sentence or question exactly as the learner should see it (capitalisation,
  spacing and punctuation included). Do not split it into tiles; the app derives tiles itself.
- translation is the meaning in the instruction language.
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


class CandidateResponse(ApiModel):
    candidates: list[CandidateOutput]


class AssessorOutput(ApiModel):
    meaning_matches: bool
    grammatical: bool
    register_ok: bool
    language_ok: bool
    issues: list[NonEmptyText] = Field(default_factory=list)


class ModelSource:
    source_id = GENERATOR_VERSION

    def __init__(
        self, client: Any, config: TextModelConfig, *, mode: str = "model"
    ) -> None:
        self.client = as_routed(client, config, kind="text")
        self.mode = mode
        self.last_route = None

    def _call(self, system_prompt: str, payload: dict, model, name: str, version: str):
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
            "approved_vocabulary": vocabulary.model_dump(mode="json"),
            "guidance": guidance.model_dump(mode="json"),
        }
        slot_guidance = []
        mission_key = (plan.mission_id, plan.practice_level, plan.content_version)
        for slot in plan.slots:
            for spec in slot.specs:
                scoped_guidance = guidance_for_slot(
                    pack, mission_key, slot.purpose, spec.construction_id
                )
                spec_data = {
                    "slot_id": slot.slot_id,
                    **spec.model_dump(mode="json", by_alias=False),
                }
                payload["specs"].append(spec_data)
                slot_guidance.append({
                    "slot_id": slot.slot_id,
                    "spec_id": spec.spec_id,
                    **scoped_guidance.model_dump(mode="json", by_alias=False),
                })
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
        specs = {
            (slot.slot_id, spec.spec_id): spec
            for slot in plan.slots
            for spec in slot.specs
        }
        returned = [(item.slot_id, item.spec_id) for item in result.candidates]
        if len(returned) != len(set(returned)) or set(returned) != set(specs):
            raise ValueError("model must return exactly one candidate for every planned spec")
        terms_by_id = {}
        for term in vocabulary.terms:
            terms_by_id[term.term_id] = term
        candidates = []
        for item in result.candidates:
            spec = specs[(item.slot_id, item.spec_id)]
            role_by_fact = {fact: role for role, fact in spec.bindings.items()}
            role_by_fact.update({
                terms_by_id[term_id].fact_id: role
                for role, term_id in spec.counterfactual.items()
                if term_id in terms_by_id
            })
            preferred_facts = set(spec.bindings.values()) | set(role_by_fact)
            term_uses = [
                use.model_copy(update={"role": role_by_fact.get(use.fact_id)})
                for use in infer_term_uses(
                    item.text, vocabulary, preferred_fact_ids=preferred_facts
                )
            ]
            candidates.append(
                CandidateSentence(
                    slot_id=item.slot_id,
                    spec_id=item.spec_id,
                    spec_use=spec.use,
                    construction_id=spec.construction_id,
                    text=item.text,
                    translation=item.translation,
                    term_uses=term_uses,
                    label_uses=spec.labels,
                    origin="model",
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
        passed = all((
            output.meaning_matches,
            output.grammatical,
            output.register_ok,
            output.language_ok,
        ))
        return LinguisticAssessment(
            status="modelAssessed",
            validator_id=ASSESSOR_VERSION,
            passed=passed,
            messages=list(output.issues),
        )
