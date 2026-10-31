"""Local, opt-in generation pipeline for language-pack lesson previews."""

from __future__ import annotations

from typing import Any

from app.ai.cache.cache import Generated, ResultCache
from app.ai.cache.features import run_cached
from app.ai.cache.store import CacheScope
from app.schemas.base import ApiModel

from .assembly import assemble_lesson
from .capabilities import LessonPlan
from .fingerprint import language_pack_feature_version, pack_fingerprint
from .generation import (
    ApprovedSentence,
    ApprovedVocabulary,
    BoundSceneFacts,
    CandidateSentence,
    LinguisticAssessment,
    assess,
    check_deterministic,
    derive_chunks,
)
from .lessons import pack_mission
from .loader import guidance_for_slot
from .model_source import ASSESSOR_VERSION, GENERATOR_VERSION, ModelSource
from .plan import bind_plan
from .schema import LanguagePack, Provenance
from .validators import STRUCTURE_VERSION, validator_versions
from .vocabulary import with_pack_vocabulary

_DEMO_CACHE_SCOPE = CacheScope.public()


class CandidateBundle(ApiModel):
    candidates: list[CandidateSentence]


class PipelineFailure(ValueError):
    def __init__(self, level: str, slot_id: str, spec_id: str, attempts: int, reasons: list[str]):
        self.level = level
        self.slot_id = slot_id
        self.spec_id = spec_id
        self.attempts = attempts
        self.reasons = reasons
        super().__init__(
            f"{level} generation failed for {slot_id}/{spec_id} after {attempts} attempt(s): "
            + "; ".join(reasons)
        )


class PilotSentence(ApiModel):
    candidate: CandidateSentence
    deterministic: Any
    assessment: LinguisticAssessment
    advisory_assessment: LinguisticAssessment | None = None


class PilotGeneration(ApiModel):
    plan: LessonPlan
    sentences: list[PilotSentence]
    approved: list[ApprovedSentence]
    result: Any
    task: Any
    payload: dict[str, Any]
    fingerprint: dict[str, Any]
    assurance: str
    mode: str
    assurance_scope: str = (
        "Structural checks and explicitly reported targeted assessments; "
        "neither structural success nor model assessment proves grammatical correctness."
    )

    @property
    def tasks(self) -> list[Any]:
        """Every task the lesson built: one, or several for a mission such as M06."""
        return list(self.task) if isinstance(self.task, list) else [self.task]


def _cached_candidates(
    source,
    cache,
    pack,
    plan,
    facts,
    vocabulary,
    guidance,
    source_id,
    fingerprint,
    cache_scope,
) -> list[CandidateSentence]:
    generation_version = getattr(source, "source_id", GENERATOR_VERSION)
    feature_fingerprint = {
        **fingerprint,
        "generator_version": generation_version,
        "assessor_version": ASSESSOR_VERSION,
        "validator_versions": validator_versions(pack.language.code, pack),
        "structure_version": STRUCTURE_VERSION,
    }
    version = language_pack_feature_version(
        "language-pack-generation",
        generation_version,
        feature_fingerprint,
    )
    payload = {
        "plan": plan.model_dump(mode="json", by_alias=False),
        "facts": facts.model_dump(mode="json", by_alias=False),
        "vocabulary": vocabulary.model_dump(mode="json", by_alias=False),
        "source": source_id,
    }

    def compute():
        candidates = source.generate(plan, facts, vocabulary, guidance, pack)
        route = getattr(source, "last_route", None)
        return Generated(
            CandidateBundle(candidates=candidates),
            route.deployment_id if route else None,
            route.model if route else None,
        )

    client = source.client
    return run_cached(
        cache,
        client,
        version=version,
        scope=cache_scope,
        payload=payload,
        compute=compute,
        decode=CandidateBundle.model_validate,
    ).candidates


def generate_pilot(
    pack: LanguagePack,
    level: str,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    source,
    *,
    plan_specs: dict[str, list[dict]] | None = None,
    builder_selection: dict[str, Any] | None = None,
    preview: bool = False,
    cache: ResultCache | None = None,
    max_repairs: int = 2,
    assess_model: bool = False,
    session_id=None,
    cache_scope: CacheScope | None = _DEMO_CACHE_SCOPE,
    mission_id: str = "M01",
    mission_context: dict[str, Any] | None = None,
) -> PilotGeneration:
    mission = pack_mission(mission_id)
    vocabulary = with_pack_vocabulary(pack, vocabulary)
    # The session seed lets a mission's own facts (M06's order) be chosen as dev does.
    context = {"seed": str(session_id or ""), **(mission_context or {})}
    facts = mission.facts(pack, level, facts, vocabulary, context)
    vocabulary = mission.vocabulary(pack, facts, vocabulary)
    proposal_mode = isinstance(source, ModelSource) and source.propose
    if proposal_mode:
        vocabulary = source.prepare(pack, level, facts, vocabulary)
    plan = bind_plan(
        pack, level, facts, vocabulary, plan_specs, str(session_id or ""), mission_id=mission_id,
    )
    mission.check_inputs(level, pack, facts, vocabulary, plan)
    mission_key = (plan.mission_id, plan.practice_level, plan.content_version)
    guidance_by_key = {}
    for slot in plan.slots:
        for spec in slot.specs:
            bundle = guidance_for_slot(pack, mission_key, slot.purpose, spec.construction_id)
            key = (slot.purpose, spec.construction_id)
            previous = guidance_by_key.get(key)
            if previous is None:
                guidance_by_key[key] = bundle.constructions[0]
            else:
                examples = {
                    item.example_id: item
                    for item in [*previous.examples, *bundle.constructions[0].examples]
                }
                mistakes = {
                    item.example_id: item
                    for item in [*previous.mistakes, *bundle.constructions[0].mistakes]
                }
                guidance_by_key[key] = previous.model_copy(
                    update={
                        "examples": list(examples.values()),
                        "mistakes": list(mistakes.values()),
                    }
                )
    constructions = list({item.construction_id: item for item in guidance_by_key.values()}.values())
    label_ids = {
        label_id for slot in plan.slots for label_id in [*slot.prompt_labels, *slot.sentence_labels]
    }
    guidance = guidance_for_slot(
        pack,
        mission_key,
        plan.slots[0].purpose,
        plan.slots[0].construction_id,
    ).model_copy(
        update={
            "labels": [label for label in pack.labels if label.semantic in label_ids],
            "constructions": constructions,
            "mission_id": plan.mission_id,
            "practice_level": plan.practice_level,
            "purpose": None,
            "prompt_labels": [],
            "sentence_labels": [],
        }
    )
    construction_ids = list(dict.fromkeys(item.construction_id for item in constructions))
    fingerprint = pack_fingerprint(pack, construction_ids, getattr(source, "source_id", ""))
    try:
        candidates = _cached_candidates(
            source,
            cache,
            pack,
            plan,
            facts,
            vocabulary,
            guidance,
            getattr(source, "source_id", "scripted-responses"),
            fingerprint,
            cache_scope,
        )
    except ValueError as exc:
        raise PipelineFailure(level, "coverage", "source-response", 1, [str(exc)]) from exc
    attempts = 0
    while True:
        assessed = []
        failures = []
        content_assessment = (
            source.review_content(pack, facts, plan, vocabulary, candidates)
            if proposal_mode else None
        )
        specs = {(slot.slot_id, spec.spec_id): spec for slot in plan.slots for spec in slot.specs}
        for candidate in candidates:
            spec = specs.get((candidate.slot_id, candidate.spec_id or candidate.slot_id))
            deterministic = check_deterministic(candidate, plan, facts, vocabulary, pack)
            assessment = assess(
                candidate,
                pack,
                vocabulary,
            )
            if content_assessment is not None:
                targeted_failures = assessment.messages if assessment.passed is False else []
                assessment = content_assessment.model_copy(update={
                    "passed": content_assessment.passed and not targeted_failures,
                    "messages": [*content_assessment.messages, *targeted_failures],
                })
            advisory_assessment = (
                source.assess(
                    candidate,
                    spec.model_dump(mode="json", by_alias=False) if spec else {},
                    guidance,
                    pack,
                )
                if assess_model and isinstance(source, ModelSource)
                else None
            )
            assessed.append((candidate, deterministic, assessment, advisory_assessment))
            reasons = list(deterministic.failures)
            accepted_assessment = (
                assessment.status
                in {
                    "reviewedForm",
                    "languageValidator",
                    "humanApproved",
                    *(["modelAssessed"] if proposal_mode else []),
                }
                and assessment.passed is True
            )
            if preview and assessment.status in {"unreviewedExample", "notAssessed"}:
                accepted_assessment = True
            if not accepted_assessment:
                reasons.extend(assessment.messages or [f"assessment status is {assessment.status}"])
            if not deterministic.passed or not accepted_assessment:
                failures.append((candidate, reasons))
        returned_order = [
            (candidate.slot_id, candidate.spec_id or candidate.slot_id) for candidate in candidates
        ]
        returned = set(returned_order)
        expected_order = list(specs)
        expected = set(expected_order)
        if len(returned_order) != len(returned):
            raise PipelineFailure(
                level,
                "coverage",
                "duplicate",
                attempts + 1,
                ["duplicate candidate specs"],
            )
        if returned != expected:
            missing = expected - returned
            unknown = returned - expected
            if unknown:
                raise PipelineFailure(
                    level,
                    "coverage",
                    "unknown",
                    attempts + 1,
                    [f"unknown candidates: {sorted(unknown)}"],
                )
            if missing:
                raise PipelineFailure(
                    level,
                    "coverage",
                    "missing",
                    attempts + 1,
                    [f"missing candidates: {sorted(missing)}"],
                )
        if returned_order != expected_order:
            raise PipelineFailure(
                level,
                "coverage",
                "order",
                attempts + 1,
                ["candidate specs are not in original planned order"],
            )
        if not failures:
            break
        if not isinstance(source, ModelSource) or attempts >= max_repairs:
            candidate, reasons = failures[0]
            raise PipelineFailure(
                level,
                candidate.slot_id,
                candidate.spec_id or candidate.slot_id,
                attempts + 1,
                [*reasons, f"Rejected sentence: {candidate.text!r}"],
            )
        attempts += 1
        failing_keys = {
            (candidate.slot_id, candidate.spec_id or candidate.slot_id) for candidate, _ in failures
        }
        repair_plan = plan.model_copy(
            update={
                "slots": [
                    slot.model_copy(
                        update={
                            "specs": [
                                spec
                                for spec in slot.specs
                                if (slot.slot_id, spec.spec_id) in failing_keys
                            ]
                        }
                    )
                    for slot in plan.slots
                    if any((slot.slot_id, spec.spec_id) in failing_keys for spec in slot.specs)
                ]
            }
        )
        repair = {
            f"{candidate.slot_id}/{candidate.spec_id}": [
                f"Previous rejected sentence: {candidate.text!r}", *reasons,
            ] for candidate, reasons in failures
        }
        try:
            fixed = source.generate(repair_plan, facts, vocabulary, guidance, pack, repair=repair)
        except ValueError as exc:
            candidate = failures[0][0]
            raise PipelineFailure(
                level,
                candidate.slot_id,
                candidate.spec_id or candidate.slot_id,
                attempts + 1,
                [str(exc)],
            ) from exc
        by_key = {
            (candidate.slot_id, candidate.spec_id or candidate.slot_id): candidate
            for candidate in candidates
        }
        by_key.update(
            {
                (candidate.slot_id, candidate.spec_id or candidate.slot_id): candidate
                for candidate in fixed
            }
        )
        candidates = list(by_key.values())

    ordered_approved = []
    sentence_reports = []
    statuses = []
    for candidate, deterministic, assessment, advisory_assessment in assessed:
        accepted_candidate = derive_chunks(
            candidate,
            pack.language.word_separator,
            phrase_chunks=candidate.slot_id in mission.phrase_slots.get(
                str(plan.practice_level), frozenset()
            ),
            phrase_boundaries=pack.language.phrase_boundaries,
        )
        ordered_approved.append(
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
        sentence_reports.append(
            PilotSentence(
                candidate=candidate,
                deterministic=deterministic,
                assessment=assessment,
                advisory_assessment=advisory_assessment,
            )
        )
        statuses.append(assessment.status)
    ordered_approved = assemble_lesson(plan, ordered_approved)
    status_order = {
        "reviewedForm": 0,
        "humanApproved": 0,
        "languageValidator": 1,
        "modelAssessed": 2,
        "unreviewedExample": 3,
        "notAssessed": 4,
    }
    assurance = max(statuses, key=lambda status: status_order.get(status, 9))
    mode = "experimentalPreview" if preview else "validated"
    if assurance in {"unreviewedExample", "notAssessed"}:
        if not preview:
            raise PipelineFailure(level, "assessment", "unassessed", attempts + 1, [assurance])
        mode = "experimentalPreview"
    if context.get("progress"):
        # Learner history the lesson reads as dev's builders do (e.g. whether plurals are taught).
        builder_selection = {"progress": context["progress"], **(builder_selection or {})}
    result, task, payload = mission.build(
        level,
        pack,
        facts,
        vocabulary,
        plan,
        ordered_approved,
        builder_selection=builder_selection,
        session_id=session_id,
    )
    payload["pilotMode"] = mode
    mission.check_lesson(level, result, ordered_approved, pack)
    if proposal_mode:
        # Inspect the actual choices, supports, feedback and grading map together;
        # isolated sentence grammar cannot establish an MCQ is unambiguous.
        rendered_review = source.review_content(pack, facts, plan, vocabulary, candidates, task)
        if rendered_review.passed is not True:
            raise PipelineFailure(level, "assembly", "content-review", attempts + 1,
                                  rendered_review.messages)
        payload["linguisticAssurance"] = (
            "Model-assessed candidate language and contextual distractors; "
            "uncertainty rejected. Not human-reviewed or proof of linguistic correctness."
        )
    ordered_reports = []
    report_by_key = {
        (item.candidate.slot_id, item.candidate.spec_id): item for item in sentence_reports
    }
    for slot in plan.slots:
        for spec in slot.specs:
            ordered_reports.append(report_by_key[(slot.slot_id, spec.spec_id)])
    return PilotGeneration(
        plan=plan,
        sentences=ordered_reports,
        approved=ordered_approved,
        result=result,
        task=task,
        payload=payload,
        fingerprint=fingerprint,
        assurance=assurance,
        mode=(f"{mode} ({getattr(source, 'mode', 'scripted/non-live')})"),
    )
