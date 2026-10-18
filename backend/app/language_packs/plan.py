"""Bind ordered mission slots to explicit scene facts."""

from __future__ import annotations

from app.schemas.enums import ProficiencyLevel

from .capabilities import LessonPlan, LessonPlanSpec, lesson_plan
from .generation import ApprovedVocabulary, BoundSceneFacts
from .schema import LanguagePack


def bind_plan(
    pack: LanguagePack,
    level: str,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan_specs: dict[str, list[dict]] | None = None,
) -> LessonPlan:
    raw_specs = plan_specs or {}
    base = lesson_plan(pack, ("M01", ProficiencyLevel(level), 1))
    known_facts = facts.all_fact_ids
    known_terms = {term.term_id for term in vocabulary.terms}
    slots = []
    for slot in base.slots:
        values = raw_specs.get(slot.slot_id)
        specs = []
        if values is None:
            values = [
                {
                    "spec_id": slot.slot_id,
                    "construction_id": slot.construction_id,
                    "bindings": slot.bindings,
                    "labels": slot.sentence_labels,
                }
            ]
        for value in values:
            spec = LessonPlanSpec(
                spec_id=value.get("spec_id", slot.slot_id),
                construction_id=value.get("construction_id", slot.construction_id),
                bindings=value.get("bindings", slot.bindings),
                counterfactual=value.get("counterfactual", {}),
                truth=value.get("truth", True),
                use=value.get("use", "answer"),
                labels=value.get("labels", slot.sentence_labels),
            )
            if spec.construction_id not in slot.construction_ids:
                raise ValueError(
                    f"spec {spec.spec_id!r} uses construction "
                    f"{spec.construction_id!r} outside slot {slot.slot_id!r}"
                )
            if unknown := set(spec.labels) - set(slot.sentence_labels):
                raise ValueError(
                    f"spec {spec.spec_id!r} uses non-sentence slot labels: "
                    f"{sorted(unknown)}"
                )
            if unknown := set(spec.bindings.values()) - known_facts:
                raise ValueError(
                    f"spec {spec.spec_id!r} binds unknown scene facts: {sorted(unknown)}"
                )
            if unknown := set(spec.counterfactual.values()) - known_terms:
                raise ValueError(
                    f"spec {spec.spec_id!r} has unknown counterfactual terms: "
                    f"{sorted(unknown)}"
                )
            specs.append(spec)
        slots.append(
            slot.model_copy(
                update={
                    "bindings": specs[0].bindings if specs else {},
                    "specs": specs,
                }
            )
        )
    return base.model_copy(update={"slots": slots})
