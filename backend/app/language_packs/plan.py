"""Bind ordered mission slots to explicit scene facts."""

from __future__ import annotations

from .capabilities import LessonPlan, LessonPlanSpec, lesson_plan, mission_template_key
from .generation import ApprovedVocabulary, BoundSceneFacts
from .schema import LanguagePack


def bind_plan(
    pack: LanguagePack,
    level: str,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan_specs: dict[str, list[dict]] | None = None,
    seed: str = "",
    mission_id: str = "M01",
) -> LessonPlan:
    if plan_specs is None:
        from .lessons import pack_mission

        plan_specs = pack_mission(mission_id).plan(pack, level, facts, vocabulary, seed)
    raw_specs = plan_specs
    base = lesson_plan(pack, mission_template_key(mission_id, level))
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
                    f"spec {spec.spec_id!r} uses non-sentence slot labels: {sorted(unknown)}"
                )
            if unknown := set(spec.bindings.values()) - known_facts:
                raise ValueError(
                    f"spec {spec.spec_id!r} binds unknown scene facts: {sorted(unknown)}"
                )
            if unknown := set(spec.counterfactual.values()) - known_terms:
                raise ValueError(
                    f"spec {spec.spec_id!r} has unknown counterfactual terms: {sorted(unknown)}"
                )
            construction = next(
                c for c in pack.constructions if c.construction_id == spec.construction_id
            )
            term_by_fact = {term.fact_id: term for term in vocabulary.terms}
            for role, fid in spec.bindings.items():
                term = term_by_fact.get(fid)
                if term is None or str(term.part_of_speech) != "noun" or role == "shown":
                    continue
                if term.provenance == "modelProposal":
                    # The content assessor checks grammatical requirements against
                    # session meaning; finite reference forms are not a prerequisite.
                    continue
                if "indefinite-article" in construction.features and not term.forms_by_key.get(
                    "article_indefinite"
                ):
                    raise ValueError(
                        f"{spec.spec_id}: selected construction needs an indefinite article"
                    )
                if "adjective-agreement" in construction.features and "attribute" in spec.bindings:
                    attribute_term = term_by_fact.get(spec.bindings["attribute"])
                    if not term.agreement or (
                        attribute_term and term.agreement not in attribute_term.forms_by_key
                    ):
                        raise ValueError(
                            f"{spec.spec_id}: selected construction needs agreeing forms"
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
