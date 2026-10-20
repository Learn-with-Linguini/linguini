"""Bind ordered mission slots to explicit scene facts."""

from __future__ import annotations

import random

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
    seed: str = "",
) -> LessonPlan:
    raw_specs = (
        plan_specs
        if plan_specs is not None
        else automatic_specs(
            pack,
            level,
            facts,
            vocabulary,
            seed,
        )
    )
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


def automatic_specs(pack, level, facts, vocabulary, seed=""):
    """Preserve the M01 slot sequence, binding every sentence before generation."""
    objects = facts.scene_facts.objects
    terms = {term.fact_id: term for term in vocabulary.terms}
    objects = [obj for obj in objects if obj.fact_id in terms]
    if len(objects) < 2:
        raise ValueError("M01 needs two confirmed translated objects")
    rng = random.Random(seed)
    raw = {}

    def add(slot, use, construction, bindings, truth=True, labels=(), counterfactual=None):
        raw.setdefault(slot, []).append(
            dict(
                spec_id=f"{slot}-{use}",
                construction_id=construction,
                use=use,
                bindings=bindings,
                truth=truth,
                labels=list(labels),
                counterfactual=counterfactual or {},
            )
        )

    attrs = [a for a in facts.scene_facts.attributes if a.fact_id in terms]
    if level == "A0":
        truths = [True, False]
        random.Random(f"{seed}:truth").shuffle(truths)
        for index, obj in enumerate(objects[:2], 1):
            other = objects[1 if index == 1 else 0]
            truth = truths[index - 1]
            add(f"matchName-{index}", "name", "identify-object", {"object": obj.fact_id})
            add(
                f"confirmName-{index}",
                "question",
                "yes-no-identification",
                {
                    "object": (obj if truth else other).fact_id,
                    "shown": obj.fact_id,
                },
                truth,
            )
            add(f"buildIdentify-{index}", "answer", "identify-object", {"object": obj.fact_id})
    elif level == "A1":
        selected = []
        for obj in objects:
            details = [a for a in attrs if a.object_fact_id == obj.fact_id]
            if details:
                # The second description prefers a non-colour detail as before.
                detail = (
                    next((a for a in details if a.kind != "colour"), details[0])
                    if selected
                    else (next((a for a in details if a.kind == "colour"), details[0]))
                )
                selected.append((obj, detail))
            if len(selected) == 2:
                break
        if len(selected) != 2:
            raise ValueError("A1 needs two translated object-detail pairs")
        for index, (obj, detail) in enumerate(selected, 1):
            other = selected[1 if index == 1 else 0][0]
            truth = rng.random() < 0.5
            slot = f"confirmObject-{index}"
            for use, named, value in (
                ("prompt", obj if truth else other, truth),
                ("answer", obj, truth),
                ("option", other, not truth),
            ):
                add(
                    slot,
                    use,
                    "yes-no-identification",
                    {
                        "object": named.fact_id,
                        "shown": obj.fact_id,
                    },
                    value,
                    [] if use == "prompt" else ["yes" if value else "no"],
                )
            add(
                "chooseAttribute" if index == 1 else "describeObject",
                "answer",
                "describe-attribute",
                {"object": obj.fact_id, "attribute": detail.fact_id},
            )
    elif level == "A2":
        relations = [r for r in facts.scene_facts.relations if r.fact_id in terms]
        if len(objects) < 3 or not (attrs or relations):
            raise ValueError(
                "A2 pack planning needs three objects and a translated detail or relation"
            )
        attr = attrs[0] if attrs else None
        first_id = attr.object_fact_id if attr else relations[0].subject_fact_id
        first = next(o for o in objects if o.fact_id == first_id)
        rel = next(
            (
                r
                for r in facts.scene_facts.relations
                if r.subject_fact_id == first.fact_id and r.fact_id in terms
            ),
            None,
        )
        second = (
            next(o for o in objects if o.fact_id == rel.reference_fact_id)
            if rel
            else next(o for o in objects if o != first)
        )
        third = next(o for o in objects if o not in (first, second))
        b1 = (
            {"object": first.fact_id, "attribute": attr.fact_id}
            if attr
            else {
                "subject": first.fact_id,
                "reference": second.fact_id,
                "relation": rel.fact_id,
            }
        )
        b2 = (
            {"subject": first.fact_id, "reference": second.fact_id, "relation": rel.fact_id}
            if rel and attr
            else {
                "object": second.fact_id,
            }
        )
        c1 = "scene-existence" if attr else "scene-location"
        c2 = "scene-location" if rel and attr else "scene-existence"
        add("chooseSceneMarker", "fact1", c1, b1)
        add("buildSceneFact", "fact2", c2, b2)
        connected = {**b1, "other-object": third.fact_id}
        add("chooseSceneDescription", "connected", "connected-description", connected)
        role = "attribute" if attr else "relation"
        contrast = next(
            (
                term
                for term in sorted(vocabulary.terms, key=lambda t: t.provenance != "modelProposal")
                if term.provenance in {"packData", "modelProposal"}
                and term.fact_id.startswith(("contrast:", "alternative:"))
                and term.linguistic.get("contrast-for") in {
                    None, attr.fact_id if attr else rel.fact_id,
                }
                and (
                    term.linguistic.get("attribute-kind") == attr.kind
                    and term.source_text != attr.value
                    if attr
                    else "relation-kind" in term.linguistic
                    and term.linguistic["relation-kind"] != str(rel.relation)
                )
            ),
            None,
        )
        if contrast is None and attr:
            alternative = next(
                (a for a in attrs if a.kind == attr.kind and a.value != attr.value), None
            )
            contrast = terms[alternative.fact_id] if alternative else None
        if contrast is None:
            raise ValueError("A2 needs an approved contrasting detail for its false option")
        add(
            "chooseSceneDescription",
            "wrongAttribute",
            "connected-description",
            connected,
            False,
            counterfactual={role: contrast.term_id},
        )
        add(
            "chooseSceneDescription",
            "falseFirst",
            c1,
            b1,
            False,
            counterfactual={role: contrast.term_id},
        )
        add(
            "chooseSceneDescription",
            "wrongExistence",
            "connected-description",
            b1,
            False,
            counterfactual={"other-object": terms[third.fact_id].term_id},
        )
        for use, construction, bindings in (
            ("fact1", c1, b1),
            ("fact2", c2, b2),
            ("fact3", "scene-existence", {"object": third.fact_id}),
        ):
            add("buildSceneDescription", use, construction, bindings)
        add("followUpSceneFact", "followup", "describe-attribute" if attr else "scene-location", b1)
    else:
        raise ValueError(f"unsupported M01 level {level}")
    return raw
