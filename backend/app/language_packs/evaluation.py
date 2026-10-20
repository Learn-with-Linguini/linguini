"""Local structural and targeted-linguistic evaluation for language packs."""

from __future__ import annotations

import hashlib
import json
import tomllib
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import ProficiencyLevel

from .capabilities import LessonPlan, LessonPlanSpec, lesson_plan
from .fingerprint import pack_fingerprint
from .generation import (
    ApprovedVocabulary,
    BoundSceneFacts,
    CandidateSentence,
    ConfirmedAttribute,
    ConfirmedObject,
    ConfirmedRelation,
    ConfirmedSceneFacts,
    assess,
    check_deterministic,
    derive_chunks,
    infer_term_uses,
)
from .loader import load_evaluation_cases, load_mission_catalog
from .model_source import GENERATOR_VERSION
from .schema import EvaluationCase, LanguagePack
from .validators import validator_versions

RUNNER_VERSION = "language-pack-evaluator.v3"
DEFAULT_THRESHOLDS = {"valid_alternative_acceptance": 1.0, "missed_rejects": 0}


class EvaluationIdentity(ApiModel):
    pack_id: NonEmptyText
    pack_version: int
    generation_content_sha256: NonEmptyText
    evaluation_file_sha256: dict[str, str]
    mission_id: NonEmptyText
    practice_level: NonEmptyText
    content_version: int
    generator_version: NonEmptyText
    runner_version: NonEmptyText
    validator_versions: dict[str, str]
    assessor_version: str | None
    thresholds: dict[str, float | int]
    thresholds_met: bool


class EvaluationRecord(ApiModel):
    identity: EvaluationIdentity
    cases_total: int
    candidates_total: int
    structural_passed: int
    linguistic_passed: int
    linguistic_assessed: int
    valid_alternatives: int
    valid_alternatives_accepted: int
    rejects: int
    rejects_structurally: int
    rejects_linguistically: int
    missed_rejects: int
    thresholds_met: bool


def _evaluation_files(pack: LanguagePack) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(pack._evaluation_files)
    }


def evaluation_identity(
    pack: LanguagePack, level: str, thresholds: dict[str, float | int] | None = None
) -> EvaluationIdentity:
    template = next(
        item for item in load_mission_catalog().missions if item.key == ("M01", level, 1)
    )
    construction_ids = list(
        dict.fromkeys(
            construction_id for slot in template.slots for construction_id in slot.construction_ids
        )
    )
    return EvaluationIdentity(
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        generation_content_sha256=hashlib.sha256(
            json.dumps(
                pack_fingerprint(pack, construction_ids, GENERATOR_VERSION),
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
        evaluation_file_sha256=_evaluation_files(pack),
        mission_id=template.mission_id,
        practice_level=level,
        content_version=template.content_version,
        generator_version=GENERATOR_VERSION,
        runner_version=RUNNER_VERSION,
        validator_versions=validator_versions(pack.language.code, pack),
        assessor_version=None,
        thresholds=thresholds or DEFAULT_THRESHOLDS,
        thresholds_met=False,
    )


def evidence_is_current(
    pack: LanguagePack,
    record: EvaluationRecord | dict[str, Any],
    mission_id: str,
    level: str,
    content_version: int,
) -> bool:
    try:
        checked = (
            record
            if isinstance(record, EvaluationRecord)
            else EvaluationRecord.model_validate(record)
        )
        current = evaluation_identity(pack, level, checked.identity.thresholds)
    except (ValueError, KeyError, StopIteration):
        return False
    return (
        checked.identity.model_copy(update={"thresholds_met": False}) == current
        and current.mission_id == mission_id
        and current.content_version == content_version
        and checked.thresholds_met
    )


def _cases_for_level(pack: LanguagePack, level: str) -> list[EvaluationCase]:
    raw_case_ids: set[str] = set()
    for path in pack._evaluation_files:
        raw = tomllib.loads(path.read_text("utf-8"))
        if (
            raw.get("mission_id") == "M01"
            and raw.get("practice_level") == level
            and raw.get("content_version") == 1
        ):
            raw_case_ids.update(item["case_id"] for item in raw.get("cases", []))
    return [case for case in load_evaluation_cases(pack) if case.case_id in raw_case_ids]


def _scene_facts(case: EvaluationCase) -> BoundSceneFacts:
    objects = [
        ConfirmedObject(
            fact_id=item.fact_id,
            scene_object_id=uuid5(NAMESPACE_URL, item.fact_id),
            label=item.concept,
            marker=index + 1,
        )
        for index, item in enumerate(case.scene.objects)
    ]
    attributes = [
        ConfirmedAttribute(
            fact_id=item.fact_id,
            object_fact_id=item.object,
            kind="colour" if item.kind.value == "color" else item.kind.value,
            value=item.value,
        )
        for item in case.scene.attributes
    ]
    relations = [
        ConfirmedRelation(
            fact_id=item.fact_id,
            subject_fact_id=item.subject,
            reference_fact_id=item.reference,
            relation=item.relation,
        )
        for item in case.scene.relations
    ]
    return BoundSceneFacts(
        scene_facts=ConfirmedSceneFacts(objects=objects, attributes=attributes, relations=relations)
    )


def _case_plan(
    pack: LanguagePack,
    level: str,
    case: EvaluationCase,
    vocabulary: ApprovedVocabulary,
    facts: BoundSceneFacts,
) -> LessonPlan:
    base = lesson_plan(pack, ("M01", ProficiencyLevel(level), 1))
    slot = next(slot for slot in base.slots if case.construction_id in slot.construction_ids)
    term_by_fact = {term.fact_id: term for term in vocabulary.terms}
    present_ids = facts.all_fact_ids
    bindings = {}
    counterfactual = {}
    for role, fact_id in case.bindings.items():
        if fact_id in present_ids:
            bindings[role] = fact_id
        else:
            term = term_by_fact.get(fact_id)
            if term is None:
                raise ValueError(f"evaluation {case.case_id} needs vocabulary for {fact_id!r}")
            counterfactual[role] = term.term_id
    asks_question = case.input.casefold().startswith(("is ", "ask ", "confirm whether")) or any(
        sentence.lstrip().startswith("¿") for sentence in case.acceptable
    )
    use = "question" if asks_question else "answer"
    if asks_question and case.construction_id == "describe-attribute":
        # As in the runtime follow-up slot, a detail question names only its subject.
        use = "followup"
    use = case.use or use
    spec = LessonPlanSpec(
        spec_id=case.case_id,
        construction_id=case.construction_id,
        bindings=bindings,
        counterfactual=counterfactual,
        truth=case.truth,
        use=use,
        labels=case.labels,
    )
    return base.model_copy(update={"slots": [slot.model_copy(update={"specs": [spec]})]})


def _candidate(
    case: EvaluationCase,
    sentence: str,
    plan: LessonPlan,
    vocabulary: ApprovedVocabulary,
) -> CandidateSentence:
    spec = plan.slots[0].specs[0]
    terms = {term.term_id: term for term in vocabulary.terms}
    role_by_fact = {}
    for role, fact in spec.bindings.items():
        # "shown" repeats the named object in yes/no specs; keep the grammatical role.
        if role != "shown" or fact not in role_by_fact:
            role_by_fact[fact] = role
    role_by_fact.update(
        {
            terms[term_id].fact_id: role
            for role, term_id in spec.counterfactual.items()
            if term_id in terms
        }
    )
    preferred = set(spec.bindings.values()) | set(role_by_fact)
    uses = [
        item.model_copy(update={"role": role_by_fact.get(item.fact_id)})
        for item in infer_term_uses(sentence, vocabulary, preferred_fact_ids=preferred)
    ]
    return CandidateSentence(
        slot_id=plan.slots[0].slot_id,
        spec_id=spec.spec_id,
        spec_use=spec.use,
        truth=spec.truth,
        construction_id=case.construction_id,
        text=sentence,
        term_uses=uses,
        label_uses=case.labels,
        origin="manual",
    )


def _assess_candidate(
    pack: LanguagePack,
    case: EvaluationCase,
    sentence: str,
    plan: LessonPlan,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
) -> tuple[bool, bool | None, list[str]]:
    try:
        candidate = _candidate(case, sentence, plan, vocabulary)
    except ValidationError as exc:
        if "candidate text must be NFC" in str(exc):
            return False, None, ["candidate text must be NFC"]
        raise
    try:
        candidate = derive_chunks(
            candidate,
            pack.language.word_separator,
            phrase_chunks=case.construction_id == "connected-description",
            phrase_boundaries=pack.language.phrase_boundaries,
        )
    except ValueError as exc:
        return False, None, [str(exc)]
    # Held-out sentences are judged as native text. Required romanization is a display
    # contract for generated candidates, so it is checked at generation, not here.
    native_pack = pack.model_copy(update={
        "language": pack.language.model_copy(update={"romanization_required": False}),
    })
    structural = check_deterministic(candidate, plan, facts, vocabulary, native_pack)
    linguistic = assess(candidate, pack, vocabulary)
    return (
        structural.passed,
        linguistic.passed
        if linguistic.status in {"languageValidator", "reviewedForm", "humanApproved"}
        else None,
        [*structural.failures, *linguistic.messages],
    )


def evaluate_pack(
    pack: LanguagePack,
    level: str,
    vocabulary: ApprovedVocabulary,
    *,
    thresholds: dict[str, float | int] | None = None,
    generation_result: Any | None = None,
) -> tuple[dict[str, Any], EvaluationRecord]:
    if generation_result is not None and str(getattr(generation_result, "mode", "")).startswith(
        "experimentalPreview"
    ):
        raise ValueError("preview generation results cannot be evaluation evidence")

    cases = _cases_for_level(pack, level)
    if not cases:
        raise ValueError(f"no evaluation cases for M01 {level}")
    report_cases = []
    valid_total = valid_accepted = reject_total = rejected_structurally = 0
    rejected_linguistically = missed = 0
    by_category: dict[str, dict[str, int]] = {}
    for case in cases:
        facts = _scene_facts(case)
        plan = _case_plan(pack, level, case, vocabulary, facts)
        slot_id = plan.slots[0].slot_id
        plan = plan.model_copy(
            update={"slots": [plan.slots[0].model_copy(update={"slot_id": slot_id})]}
        )
        acceptable_results = []
        for sentence in case.acceptable:
            structural, linguistic, reasons = _assess_candidate(
                pack, case, sentence, plan, facts, vocabulary
            )
            valid_total += 1
            accepted = structural and linguistic is True
            valid_accepted += int(accepted)
            acceptable_results.append(
                {
                    "sentence": sentence,
                    "structural_pass": structural,
                    "linguistic_pass": linguistic,
                    "accepted": accepted,
                    "reasons": reasons,
                }
            )
        reject_results = []
        for reject in case.reject:
            structural, linguistic, reasons = _assess_candidate(
                pack, case, reject.sentence, plan, facts, vocabulary
            )
            reject_total += 1
            if not structural:
                classification = "structural"
                rejected_structurally += 1
            elif linguistic is False:
                classification = "linguistic"
                rejected_linguistically += 1
            else:
                classification = "missed"
                missed += 1
            category_counts = by_category.setdefault(
                reject.category,
                {"structurally_rejected": 0, "linguistically_rejected": 0, "missed": 0},
            )
            key = {
                "structural": "structurally_rejected",
                "linguistic": "linguistically_rejected",
                "missed": "missed",
            }[classification]
            category_counts[key] += 1
            reject_results.append(
                {
                    "sentence": reject.sentence,
                    "category": reject.category,
                    "classification": classification,
                    "structural_pass": structural,
                    "linguistic_pass": linguistic,
                    "reasons": reasons,
                }
            )
        report_cases.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "input": case.input,
                "acceptable": acceptable_results,
                "reject": reject_results,
            }
        )
    configured_thresholds = thresholds or DEFAULT_THRESHOLDS
    accepted_fraction = valid_accepted / valid_total if valid_total else 0
    thresholds_met = accepted_fraction >= float(
        configured_thresholds["valid_alternative_acceptance"]
    ) and missed <= int(configured_thresholds["missed_rejects"])
    structural_passed = sum(
        int(item["structural_pass"]) for case in report_cases for item in case["acceptable"]
    ) + sum(int(item["structural_pass"]) for case in report_cases for item in case["reject"])
    linguistic_passed = sum(
        int(item["linguistic_pass"] is True) for case in report_cases for item in case["acceptable"]
    ) + sum(
        int(item["linguistic_pass"] is True) for case in report_cases for item in case["reject"]
    )
    identity = evaluation_identity(pack, level, configured_thresholds).model_copy(
        update={"thresholds_met": thresholds_met}
    )
    record = EvaluationRecord(
        identity=identity,
        cases_total=len(cases),
        candidates_total=valid_total + reject_total,
        structural_passed=structural_passed,
        linguistic_passed=linguistic_passed,
        linguistic_assessed=sum(
            item["linguistic_pass"] is not None
            for case in report_cases
            for item in [*case["acceptable"], *case["reject"]]
        ),
        valid_alternatives=valid_total,
        valid_alternatives_accepted=valid_accepted,
        rejects=reject_total,
        rejects_structurally=rejected_structurally,
        rejects_linguistically=rejected_linguistically,
        missed_rejects=missed,
        thresholds_met=thresholds_met,
    )
    return (
        {
            "mission_id": "M01",
            "practice_level": level,
            "structural": {
                "candidates": valid_total + reject_total,
                "candidates_passed": structural_passed,
                "valid_alternatives": valid_total,
                "valid_alternatives_accepted": valid_accepted,
                "rejects": reject_total,
                "rejects_rejected": rejected_structurally,
                "rejects_missed": missed,
                "by_category": by_category,
            },
            "linguistic": {
                "candidates": valid_total + reject_total,
                "assessed": record.linguistic_assessed,
                "candidates_passed": linguistic_passed,
                "rejects_rejected": rejected_linguistically,
                "validator": validator_versions(pack.language.code, pack),
                "scope": "targeted checks, not a complete grammaticality judgement",
            },
            "cases": report_cases,
            "thresholds_met": thresholds_met,
            "evaluation_record": record.model_dump(mode="json", by_alias=False),
        },
        record,
    )
