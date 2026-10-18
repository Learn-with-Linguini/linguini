"""Mission capability checks for an explicitly loaded language pack."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from pydantic import Field

from app.config import get_language_pack_releases
from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import ProficiencyLevel

from .loader import LanguagePackError, load_mission_catalog
from .schema import LanguagePack, MissionKey, MissionSlotTemplate


class MissionCapability(MissionKey):
    supported: bool
    structurally_supported: bool
    missing_constructions: list[str]
    outdated_constructions: list[str]
    missing_labels: list[str]
    unreviewed_items: list[str]
    examples_present: bool
    review_complete: bool
    evaluation_current: bool
    allowlisted: bool
    blockers: list[str]
    release_ready: bool
    release_enabled: bool


class LessonPlanSpec(ApiModel):
    spec_id: NonEmptyText
    construction_id: NonEmptyText
    bindings: dict[str, str] = Field(default_factory=dict)
    counterfactual: dict[str, str] = Field(default_factory=dict)
    truth: bool = True
    use: NonEmptyText = "answer"
    labels: list[str] = Field(default_factory=list)


class LessonPlanSlot(MissionSlotTemplate):
    slot_id: NonEmptyText
    bindings: dict[str, str] = Field(default_factory=dict)
    specs: list[LessonPlanSpec] = Field(default_factory=list)


class LessonPlan(MissionKey):
    slots: list[LessonPlanSlot]
    required_constructions: list[str]
    required_labels: list[str]


def _required_material_review_status(
    pack: LanguagePack, required_ids: set[str], template
) -> list[str]:
    unreviewed = []
    if pack.provenance.review_status != "humanReviewed":
        unreviewed.append("pack")
    for label in pack.labels:
        if label.semantic in required_ids and label.provenance.review_status != "humanReviewed":
            unreviewed.append(f"label:{label.semantic}")
    for construction in pack.constructions:
        if construction.construction_id not in required_ids:
            continue
        if construction.provenance.review_status != "humanReviewed":
            unreviewed.append(f"construction:{construction.construction_id}")
        in_scope_purposes = {
            slot.purpose
            for slot in template.slots
            if construction.construction_id in slot.construction_ids
        }
        for example in construction.examples:
            if (
                str(template.practice_level) in example.levels
                and set(example.purposes) & in_scope_purposes
                and example.provenance.review_status != "humanReviewed"
            ):
                unreviewed.append(f"example:{example.example_id}")
        for example in construction.mistakes:
            if (
                str(template.practice_level) in example.levels
                and set(example.purposes) & in_scope_purposes
                and example.provenance.review_status != "humanReviewed"
            ):
                unreviewed.append(f"incorrect:{example.example_id}")
    return unreviewed


def mission_capability(
    pack: LanguagePack,
    mission_key: tuple[str, ProficiencyLevel | str, int] | MissionKey,
    release_allowlist: Iterable[tuple[str, str, str]] | None = None,
    evaluation_record: dict | None = None,
) -> MissionCapability:
    if isinstance(mission_key, MissionKey):
        level = getattr(mission_key.practice_level, "value", mission_key.practice_level)
        key = (
            mission_key.mission_id,
            str(level),
            mission_key.content_version,
        )
    else:
        level = getattr(mission_key[1], "value", mission_key[1])
        key = (mission_key[0], str(level), mission_key[2])
    template = next(
        (item for item in load_mission_catalog().missions if item.key == key),
        None,
    )
    if template is None:
        raise LanguagePackError("<mission catalog>", "/", f"unknown mission key {key}")

    constructions = {item.construction_id: item for item in pack.constructions}
    missing_constructions = []
    outdated_constructions = []
    for requirement in template.required_constructions:
        found = constructions.get(requirement.construction_id)
        if found is None:
            missing_constructions.append(requirement.construction_id)
        elif found.version < requirement.min_version:
            outdated_constructions.append(requirement.construction_id)
    labels = {label.semantic for label in pack.labels}
    missing_labels = sorted(set(template.required_labels) - labels)
    supported = not (missing_constructions or outdated_constructions or missing_labels)
    required_ids = {item.construction_id for item in template.required_constructions}
    required_ids.update(template.required_labels)
    unreviewed_items = _required_material_review_status(pack, required_ids, template)
    examples_present = all(
        any(
            str(template.practice_level) in example.levels
            and set(example.purposes)
            & {
                slot.purpose
                for slot in template.slots
                if requirement.construction_id in slot.construction_ids
            }
            for example in construction.examples
        )
        and any(
            str(template.practice_level) in example.levels
            and set(example.purposes)
            & {
                slot.purpose
                for slot in template.slots
                if requirement.construction_id in slot.construction_ids
            }
            for example in construction.mistakes
        )
        for requirement in template.required_constructions
        if (construction := constructions.get(requirement.construction_id)) is not None
    )
    review_complete = not unreviewed_items
    configured_allowlist = (
        get_language_pack_releases() if release_allowlist is None else set(release_allowlist)
    )
    allowlisted = (
        pack.language.code, template.mission_id, str(template.practice_level)
    ) in configured_allowlist
    from .evaluation import evidence_is_current

    evaluation_current = bool(
        evaluation_record
        and evidence_is_current(
            pack,
            evaluation_record,
            template.mission_id,
            str(template.practice_level),
            template.content_version,
        )
    )
    blockers = []
    if not supported:
        blockers.append("required constructions or labels are missing or outdated")
    if not examples_present:
        blockers.append("required constructions lack in-scope examples or mistakes")
    if not review_complete:
        blockers.append(f"{len(unreviewed_items)} items need fluent human review")
    if evaluation_record is None:
        blockers.append("no evaluation evidence")
    elif not evaluation_current:
        blockers.append("evaluation evidence is stale or thresholds are not met")
    if not allowlisted:
        blockers.append("mission is not allowlisted")
    release_ready = (
        supported and examples_present and review_complete and evaluation_current and allowlisted
    )
    return MissionCapability(
        mission_id=template.mission_id,
        practice_level=template.practice_level,
        content_version=template.content_version,
        supported=supported,
        structurally_supported=supported,
        missing_constructions=missing_constructions,
        outdated_constructions=outdated_constructions,
        missing_labels=missing_labels,
        unreviewed_items=unreviewed_items,
        examples_present=examples_present,
        review_complete=review_complete,
        evaluation_current=evaluation_current,
        allowlisted=allowlisted,
        blockers=blockers,
        release_ready=release_ready,
        release_enabled=release_ready,
    )


def lesson_plan(
    pack: LanguagePack,
    mission_key: tuple[str, ProficiencyLevel | str, int],
    slot_bindings: dict[str, dict[str, str]] | None = None,
) -> LessonPlan:
    level = getattr(mission_key[1], "value", mission_key[1])
    key = (mission_key[0], str(level), mission_key[2])
    template = next(
        (item for item in load_mission_catalog().missions if item.key == key),
        None,
    )
    if template is None:
        raise LanguagePackError("<mission catalog>", "/", f"unknown mission key {key}")
    supplied = slot_bindings or {}
    expanded_slots = [
        slot_template
        for _ in range(template.sequence_repeat)
        for slot_template in template.slots
        for _ in range(slot_template.repeat)
    ]
    purpose_counts = Counter(slot.purpose for slot in expanded_slots)
    purpose_occurrences: Counter[str] = Counter()
    slots = []
    for slot_template in expanded_slots:
        purpose_occurrences[slot_template.purpose] += 1
        slot_id = slot_template.purpose
        if purpose_counts[slot_id] > 1:
            slot_id = f"{slot_id}-{purpose_occurrences[slot_id]}"
        slots.append(
            LessonPlanSlot(
                slot_id=slot_id,
                purpose=slot_template.purpose,
                construction_id=slot_template.construction_id,
                additional_constructions=slot_template.additional_constructions,
                target_ids=slot_template.target_ids,
                prompt_labels=slot_template.prompt_labels,
                sentence_labels=slot_template.sentence_labels,
                bindings=supplied.get(slot_id, {}),
            )
        )
    return LessonPlan(
        mission_id=template.mission_id,
        practice_level=template.practice_level,
        content_version=template.content_version,
        slots=slots,
        required_constructions=[
            item.construction_id for item in template.required_constructions
        ],
        required_labels=template.required_labels,
    )
