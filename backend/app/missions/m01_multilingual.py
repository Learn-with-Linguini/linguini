"""Routing and contract validation for the staged multilingual M01 path."""

from __future__ import annotations

import logging
import os
import tomllib
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.languages import get_language, languages
from app.missions import get_mission
from app.schemas.base import ApiModel
from app.schemas.enums import ProficiencyLevel
from app.schemas.languages import Language
from app.schemas.mission_m01_contract import (
    M01ContractInput,
    M01ContractOutput,
    M01GeneratedLesson,
    SentenceChunk,
    fact_id,
)
from app.schemas.missions import MissionDefinition
from app.schemas.tasks import EvidenceType, QuestionEvaluation

CONTRACT_VERSION = "m01-multilingual.v1"
M01_PLAN_PATH = Path(__file__).with_name("m01_multilingual.toml")

type M01VariantKey = tuple[str, str, int]


@dataclass(frozen=True)
class M01Variant:
    practice_level: ProficiencyLevel
    content_version: int
    contract_version: str
    communication_goal: str


M01_VARIANTS: dict[M01VariantKey, M01Variant] = {
    ("M01", "A0", 1): M01Variant(
        ProficiencyLevel.A0,
        1,
        CONTRACT_VERSION,
        "recognise familiar object names and identify objects using taught chunks",
    ),
    ("M01", "A1", 1): M01Variant(
        ProficiencyLevel.A1,
        1,
        CONTRACT_VERSION,
        "identify and describe an object using confirmed details",
    ),
    ("M01", "A2", 1): M01Variant(
        ProficiencyLevel.A2,
        1,
        CONTRACT_VERSION,
        "connect confirmed facts into a short scene description and answer a follow-up",
    ),
}
M01_LEVELS = frozenset(
    level for mission, level, _version in M01_VARIANTS if mission == "M01"
)
logger = logging.getLogger(__name__)


class UnroutedMissionVariant(LookupError):
    """A mission level/version without an explicit route."""


class MissionContractError(ValueError):
    """A multilingual M01 input or output violates the contract."""


type M01FactKind = Literal["object", "attribute", "relation", "count"]
type M01Interaction = Literal["multipleChoice", "markerChoice", "sentenceBuilding"]


class M01QuestionSlot(ApiModel):
    purpose: str
    target_ids: list[str] = Field(min_length=1)
    interaction: M01Interaction
    evidence: EvidenceType
    criteria: list[str] = Field(min_length=1)
    focus: Annotated[int, Field(ge=1)]
    options: tuple[Annotated[int, Field(ge=2)], Annotated[int, Field(ge=2)]] | None = None
    distractor_chunks: tuple[
        Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]
    ] | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> M01QuestionSlot:
        if self.interaction == "sentenceBuilding":
            if self.options is not None or self.distractor_chunks is None:
                raise ValueError("sentence-building slots require distractor_chunks only")
            lower, upper = self.distractor_chunks
        else:
            if self.distractor_chunks is not None or self.options is None:
                raise ValueError("choice slots require options only")
            lower, upper = self.options
        if lower > upper:
            raise ValueError("slot count range minimum cannot exceed its maximum")
        return self


class M01PreparationPlan(ApiModel):
    per_object: bool
    extra_cards: Annotated[int, Field(ge=0)]


class M01LevelPlan(ApiModel):
    level: ProficiencyLevel
    plan_version: int
    content_version: int
    fact_kinds: list[M01FactKind]
    min_objects: Annotated[int, Field(ge=1)]
    min_detail_facts: Annotated[int, Field(ge=0)]
    focus_objects: Annotated[int, Field(ge=1)]
    questions: list[M01QuestionSlot] = Field(min_length=1)
    preparation: M01PreparationPlan
    max_answer_chunks: Annotated[int, Field(ge=1)]
    min_connected_facts: Annotated[int, Field(ge=1)] | None = None


@cache
def load_m01_level_plan(level: ProficiencyLevel | str) -> M01LevelPlan:
    normalized = str(level).upper()
    data = tomllib.loads(M01_PLAN_PATH.read_text(encoding="utf-8"))
    try:
        raw = data["levels"][normalized]
    except KeyError:
        raise MissionContractError(f"no M01 generation plan for {normalized}") from None
    variant = m01_variant("M01", normalized, raw["content_version"])
    if variant.content_version != raw["content_version"]:
        raise MissionContractError(f"M01 plan content version mismatch for {normalized}")
    plan = M01LevelPlan.model_validate({
        **raw,
        "level": normalized,
        "plan_version": data["plan_version"],
    })
    definition = get_mission("M01", normalized, plan.content_version)
    if definition is None:
        raise MissionContractError(f"no M01 definition for {normalized}")
    defined_targets = set(definition.targets)
    slot_targets = {
        target_id for slot in plan.questions for target_id in slot.target_ids
    }
    unknown_targets = slot_targets - defined_targets
    if unknown_targets:
        raise MissionContractError(
            f"M01 {normalized} plan references undefined targets: {sorted(unknown_targets)}"
        )
    for group in definition.expected_performance.required_target_groups:
        if not set(group) & slot_targets:
            raise MissionContractError(
                f"M01 {normalized} plan does not cover required target group {group}"
            )
    if len(plan.questions) < definition.expected_performance.min_assessed_questions:
        raise MissionContractError(
            f"M01 {normalized} plan has fewer slots than required assessed questions"
        )
    if plan.min_objects != definition.photo_requirements.min_confirmed_objects:
        raise MissionContractError(
            f"M01 {normalized} plan min_objects must match photo requirements"
        )
    if plan.focus_objects > plan.min_objects:
        raise MissionContractError(
            f"M01 {normalized} plan focus_objects cannot exceed min_objects"
        )
    defined_criteria = {item.criterion_id for item in definition.evaluation_criteria}
    unknown_criteria = {
        criterion
        for slot in plan.questions
        for criterion in slot.criteria
        if criterion not in defined_criteria
    }
    if unknown_criteria:
        raise MissionContractError(
            f"M01 {normalized} plan references undefined evaluation criteria: "
            f"{sorted(unknown_criteria)}"
        )
    if any(slot.focus > plan.focus_objects for slot in plan.questions):
        raise MissionContractError(
            f"M01 {normalized} plan question focus exceeds focus_objects"
        )
    return plan


def m01_variant(
    mission_id: str, level: ProficiencyLevel | str, version: int
) -> M01Variant:
    key = mission_id, str(level), version
    try:
        return M01_VARIANTS[key]
    except KeyError:
        raise UnroutedMissionVariant(f"no multilingual M01 route for {key}") from None


def generation_enabled() -> bool:
    return os.getenv("MULTILINGUAL_ENABLED", "false").strip().lower() == "true"


@cache
def _parse_m01_combinations(raw_combinations: str) -> frozenset[tuple[str, str]]:
    parsed: set[tuple[str, str]] = set()
    if not raw_combinations.strip():
        return frozenset()
    known_languages = {item.code.casefold() for item in languages()}
    for raw_entry in raw_combinations.split(","):
        entry = raw_entry.strip()
        if entry == "*":
            parsed.add(("*", "*"))
            continue
        parts = entry.split(":")
        if (
            len(parts) != 2
            or not parts[0].strip()
            or parts[0].strip() == "*"
            or parts[1].strip().upper() not in {*M01_LEVELS, "*"}
        ):
            logger.warning(
                "Ignoring malformed MULTILINGUAL_COMBINATIONS entry %r.",
                entry,
            )
            continue
        code, configured_level = parts[0].strip(), parts[1].strip().upper()
        if code.casefold() not in known_languages:
            logger.warning(
                "Ignoring malformed MULTILINGUAL_COMBINATIONS entry %r.",
                entry,
            )
            continue
        parsed.add((code.casefold(), configured_level))
    return frozenset(parsed)


def m01_generation_enabled_for(language: str, level: str) -> bool:
    if not generation_enabled():
        return False
    target = get_language(language)
    normalized_level = str(level).strip().upper()
    if target is None or normalized_level not in M01_LEVELS:
        return False

    combinations = _parse_m01_combinations(
        os.getenv("MULTILINGUAL_COMBINATIONS", "")
    )
    return ("*", "*") in combinations or (
        (target.code.casefold(), "*") in combinations
        or (target.code.casefold(), normalized_level) in combinations
    )

def validate_contract_input(contract: M01ContractInput) -> MissionDefinition:
    """Validate registry and mission routing after model-level structural checks."""
    target = get_language(contract.target_language)
    instruction = get_language(contract.instruction_language)
    if target is None:
        raise MissionContractError(f"unregistered target language: {contract.target_language}")
    if instruction is None:
        raise MissionContractError(
            f"unregistered instruction language: {contract.instruction_language}"
        )
    if target.code.casefold() == instruction.code.casefold():
        raise MissionContractError("target and instruction languages must differ")
    if not instruction.instruction:
        raise MissionContractError("instruction language is not enabled for instruction")

    mission_ref = contract.mission
    m01_variant(mission_ref.mission_id, mission_ref.practice_level, mission_ref.content_version)
    mission = get_mission(
        mission_ref.mission_id, mission_ref.practice_level, mission_ref.content_version
    )
    if mission is None:
        raise MissionContractError(
            "mission definition does not exist for "
            f"{mission_ref.mission_id}/{mission_ref.practice_level}/{mission_ref.content_version}"
        )
    return mission


def join_chunks(chunks: list[SentenceChunk]) -> str:
    """Join chunks according to each non-first chunk's join instruction."""
    if not chunks:
        return ""
    result = chunks[0].text
    for chunk in chunks[1:]:
        result += (" " if chunk.join == "space" else "") + chunk.text
    return result


def default_join(language: Language | str, text: str) -> str:
    """Choose a chunk join; elision is intentionally a builder-owned decision."""
    language_entry = get_language(language) if isinstance(language, str) else language
    if language_entry is not None and language_entry.word_separator == "none":
        return "none"
    first = next((character for character in text if not character.isspace()), "")
    if first and unicodedata.category(first).startswith("P"):
        return "none"
    return "space"


def convert_generated_lesson(
    contract: M01ContractInput, generated: M01GeneratedLesson
) -> M01ContractOutput:
    definition = validate_contract_input(contract)
    plan = load_m01_level_plan(contract.mission.practice_level)
    objects = {item.fact_id: item for item in contract.scene_facts.objects}
    terms_by_fact: dict[str, list] = {}
    for term in contract.vocabulary:
        terms_by_fact.setdefault(term.fact_id, []).append(term)

    questions = []
    answers = {}
    evaluations = []
    if len(generated.questions) != len(plan.questions):
        raise MissionContractError(
            f"question count {len(generated.questions)} does not match plan "
            f"{len(plan.questions)}"
        )
    for index, question in enumerate(generated.questions):
        slot = plan.questions[index]
        for target_id in question.target_ids:
            if target_id not in definition.targets:
                raise MissionContractError(f"unknown target: {target_id}")

        questions.append({
            "question_id": question.question_id,
            "target_ids": question.target_ids,
            "section": question.section,
            "prompt": question.prompt,
            "prompt_translation": question.prompt_translation,
            "instruction": question.instruction,
            "interaction": question.interaction,
            "options": question.options,
            "marker_fact_ids": (
                {item.option_id: item.fact_id for item in question.marker_options}
                if question.interaction == "markerChoice" else None
            ),
            "chunks": question.chunks,
            "fact_ids": question.fact_ids,
            "feedback": question.feedback,
        })
        answers[question.question_id] = question.answer
        first_object = next(
            (objects[fact] for fact in question.fact_ids if fact in objects),
            None,
        )
        vocabulary_ids = list(dict.fromkeys(
            term.vocabulary_item_id
            for fact in question.fact_ids
            for term in terms_by_fact.get(fact, [])
            if term.vocabulary_item_id is not None
        ))
        evaluations.append(QuestionEvaluation(
            question_id=question.question_id,
            objective_id=definition.objective.objective_id,
            target_ids=question.target_ids,
            evidence_type=slot.evidence,
            rubric_criterion_ids=slot.criteria,
            vocabulary_item_ids=vocabulary_ids,
            scene_object_id=first_object.scene_object_id if first_object else None,
            corrections=question.feedback.corrections,
            correct_note=question.feedback.correct,
        ))

    return M01ContractOutput(
        contract_version=CONTRACT_VERSION,
        mission=contract.mission,
        target_language=contract.target_language,
        instruction_language=contract.instruction_language,
        objective_id=definition.objective.objective_id,
        title=generated.title,
        explanation=generated.explanation,
        preparation=generated.preparation,
        questions=questions,
        private={"answers": answers, "evaluations": evaluations},
    )


def _fact_ids(contract: M01ContractInput) -> set[str]:
    return contract.scene_facts.all_fact_ids


def _check_fact_references(
    references: list[str], valid_fact_ids: set[str], source: str
) -> None:
    if unknown := set(references) - valid_fact_ids:
        raise MissionContractError(f"{source} references unknown scene facts: {sorted(unknown)}")


def _check_evaluation(
    mission: MissionDefinition, evaluation: QuestionEvaluation
) -> None:
    try:
        mission.check_evaluation(evaluation)
    except ValueError as exc:
        raise MissionContractError(str(exc)) from exc


def validate_contract_output(
    contract: M01ContractInput,
    output: M01ContractOutput,
    plan: M01LevelPlan | None = None,
) -> None:
    """Validate generated output against the confirmed input and M01 definition."""
    definition = validate_contract_input(contract)
    if (
        output.mission != contract.mission
        or output.target_language.casefold() != contract.target_language.casefold()
        or output.instruction_language.casefold() != contract.instruction_language.casefold()
    ):
        raise MissionContractError("output mission and languages must match the input")
    if output.objective_id != definition.objective.objective_id:
        raise MissionContractError("output objective does not match the mission definition")

    valid_fact_ids = _fact_ids(contract)
    object_facts = {item.fact_id: item for item in contract.scene_facts.objects}
    for card in output.preparation:
        _check_fact_references(card.fact_ids, valid_fact_ids, "preparation card")

    target_ids = set(definition.targets)
    question_ids = [question.question_id for question in output.questions]
    if len(question_ids) != len(set(question_ids)):
        raise MissionContractError("question IDs must be unique")
    if (
        plan is None
        and len(output.questions) < definition.expected_performance.min_assessed_questions
    ):
        raise MissionContractError("output has fewer than the required assessed questions")

    covered_targets: set[str] = set()
    for question in output.questions:
        unknown_targets = set(question.target_ids) - target_ids
        if unknown_targets:
            raise MissionContractError(
                f"question targets do not belong to this mission: {sorted(unknown_targets)}"
            )
        covered_targets.update(question.target_ids)
        _check_fact_references(question.fact_ids, valid_fact_ids, "question")

        option_ids = [option.option_id for option in question.options]
        if len(option_ids) != len(set(option_ids)):
            raise MissionContractError("question option IDs must be unique")
        chunk_ids = [chunk.chunk_id for chunk in question.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise MissionContractError("chunk IDs must be unique per question")

        if question.interaction == "markerChoice":
            if question.marker_fact_ids is None:
                raise MissionContractError("markerChoice questions require marker facts")
            if set(question.marker_fact_ids) != set(option_ids):
                raise MissionContractError("marker facts must cover exactly the offered options")
            _check_fact_references(
                list(question.marker_fact_ids.values()), valid_fact_ids, "marker choice"
            )
            for fact_id in question.marker_fact_ids.values():
                object_fact = object_facts.get(fact_id)
                if object_fact is None:
                    raise MissionContractError("marker choices must map to object facts")
                if object_fact.marker is None:
                    raise MissionContractError(
                        "marker choice objects must have review markers"
                    )
        elif question.marker_fact_ids is not None:
            raise MissionContractError("marker facts are only valid for markerChoice questions")

    for group in definition.expected_performance.required_target_groups:
        if not set(group) & covered_targets:
            raise MissionContractError("output does not cover every required target group")

    answers = output.private.answers
    if set(answers) != set(question_ids):
        raise MissionContractError("every question must have exactly one private answer")
    question_by_id = {question.question_id: question for question in output.questions}
    for question_id, question in question_by_id.items():
        answer = answers[question_id]
        option_ids = {option.option_id for option in question.options}
        if question.interaction in {"multipleChoice", "markerChoice"}:
            if answer.correct_option_id not in option_ids:
                raise MissionContractError("private answer must be one of the offered options")
        if question.interaction == "sentenceBuilding":
            if not answer.chunk_ids:
                raise MissionContractError("sentence-building answers need ordered chunk IDs")
            if len(answer.chunk_ids) != len(set(answer.chunk_ids)):
                raise MissionContractError("sentence-building answer chunk IDs cannot repeat")
            if not set(answer.chunk_ids) <= {chunk.chunk_id for chunk in question.chunks}:
                raise MissionContractError(
                    "sentence-building answers must use offered question chunks"
                )

    evaluations = output.private.evaluations
    evaluation_ids = [evaluation.question_id for evaluation in evaluations]
    if len(evaluation_ids) != len(set(evaluation_ids)) or set(evaluation_ids) != set(question_ids):
        raise MissionContractError("there must be one evaluation per question")
    for evaluation in evaluations:
        _check_evaluation(definition, evaluation)
    _validate_explanation_does_not_reveal_answers(output)
    if plan is not None:
        _validate_planned_output(contract, definition, output, plan)

    preparation_plan = plan or load_m01_level_plan(contract.mission.practice_level)
    if preparation_plan.preparation.per_object:
        object_fact_ids = set(object_facts)
        assessed_objects = {
            fact_ref
            for question in output.questions
            for fact_ref in (
                *question.fact_ids,
                *(question.marker_fact_ids or {}).values(),
            )
            if fact_ref in object_fact_ids
        }
        taught_objects = {
            fact_ref
            for card in output.preparation
            for fact_ref in card.fact_ids
            if fact_ref in object_fact_ids
        }
        if assessed_objects - taught_objects:
            raise MissionContractError(
                "preparation cards must teach every assessed object before assessment"
            )


def _fold_contract_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _answer_text_without_trailing_punctuation(value: str) -> str:
    normalized = _fold_contract_text(value)
    while normalized and unicodedata.category(normalized[-1]).startswith("P"):
        normalized = normalized[:-1].rstrip()
    return normalized


def _validate_explanation_does_not_reveal_answers(output: M01ContractOutput) -> None:
    if output.explanation is None:
        return

    explanation = _fold_contract_text(output.explanation)
    preparation_texts = {_fold_contract_text(card.text) for card in output.preparation}
    for question in output.questions:
        answer = output.private.answers[question.question_id]
        if question.interaction == "sentenceBuilding":
            chunks_by_id = {chunk.chunk_id: chunk for chunk in question.chunks}
            answer_text = join_chunks([chunks_by_id[chunk_id] for chunk_id in answer.chunk_ids])
        else:
            answer_text = next(
                option.label
                for option in question.options
                if option.option_id == answer.correct_option_id
            )

        normalized_answer = _answer_text_without_trailing_punctuation(answer_text)
        if (
            not normalized_answer
            or normalized_answer in preparation_texts
            or normalized_answer not in explanation
        ):
            continue
        raise MissionContractError(
            f"explanation reveals the answer to {question.question_id}"
        )


def _validate_planned_output(contract, definition, output, plan) -> None:
    if output.mission.content_version != plan.content_version:
        raise MissionContractError("plan content version does not match the mission")
    expected_questions = len(plan.questions)
    if len(output.questions) != expected_questions:
        raise MissionContractError(
            f"question count {len(output.questions)} does not match plan {expected_questions}"
        )
    expected_preparation = (
        len(contract.scene_facts.objects) + plan.preparation.extra_cards
        if plan.preparation.per_object else plan.preparation.extra_cards
    )
    if len(output.preparation) != expected_preparation:
        raise MissionContractError(
            f"preparation-card count {len(output.preparation)} is outside "
            f"{expected_preparation}–{expected_preparation}"
        )
    facts = {
        **{item.fact_id: "object" for item in contract.scene_facts.objects},
        **{item.fact_id: "attribute" for item in contract.scene_facts.attributes},
        **{item.fact_id: "relation" for item in contract.scene_facts.relations},
        **{item.fact_id: "count" for item in contract.scene_facts.counted_groups},
    }
    objects_by_fact = {item.fact_id: item for item in contract.scene_facts.objects}
    object_fact_ids = set(objects_by_fact)
    terms_by_fact: dict[str, list] = {}
    for term in contract.vocabulary:
        terms_by_fact.setdefault(term.fact_id, []).append(term)
    approved_colour_fact_objects = {
        item.fact_id: item.object_fact_id
        for item in contract.scene_facts.attributes
        if item.kind == "colour" and item.fact_id in terms_by_fact
    }
    allowed_kinds = set(plan.fact_kinds)

    references = [
        *(("preparation card", card.fact_ids) for card in output.preparation),
        *(("question", question.fact_ids) for question in output.questions),
    ]
    for source, fact_ids in references:
        if any(facts[fact_id] not in allowed_kinds for fact_id in fact_ids):
            raise MissionContractError(f"{source} references a fact kind outside the plan")

    covered_targets: set[str] = set()
    focus_candidates: dict[int, set[str]] = {}
    colour_focus_indices: set[int] = set()
    for index, (question, slot) in enumerate(
        zip(output.questions, plan.questions, strict=True), start=1,
    ):
        if question.target_ids != slot.target_ids:
            raise MissionContractError(
                f"question {index} targets do not match plan slot {slot.purpose}"
            )
        if question.interaction != slot.interaction:
            raise MissionContractError(
                f"question {index} interaction does not match plan slot {slot.purpose}"
            )
        covered_targets.update(question.target_ids)
        choice = question.interaction in {"multipleChoice", "markerChoice"}
        if choice:
            if question.chunks:
                raise MissionContractError("choice questions cannot have chunks")
            minimum, maximum = slot.options
            if not minimum <= len(question.options) <= maximum:
                raise MissionContractError(
                    f"option count {len(question.options)} is outside "
                    f"{minimum}–{maximum} for {slot.purpose}"
                )
            labels = [_fold_contract_text(option.label) for option in question.options]
            if len(labels) != len(set(labels)):
                raise MissionContractError("choice labels must be distinct")
        elif question.options:
            raise MissionContractError("sentenceBuilding questions cannot have options")

        answer = output.private.answers[question.question_id]
        if choice:
            correct_text = next(
                option.label for option in question.options
                if option.option_id == answer.correct_option_id
            )
        else:
            chunks = {chunk.chunk_id: chunk for chunk in question.chunks}
            if len(answer.chunk_ids) > plan.max_answer_chunks:
                raise MissionContractError("answer uses too many chunks")
            distractors = len(question.chunks) - len(answer.chunk_ids)
            minimum, maximum = slot.distractor_chunks
            if not minimum <= distractors <= maximum:
                raise MissionContractError(
                    f"distractor-chunk count {distractors} is outside "
                    f"{minimum}–{maximum} for {slot.purpose}"
                )
            if any(not chunk.text.strip() for chunk in question.chunks):
                raise MissionContractError("sentence chunks must contain text")
            correct_text = join_chunks([chunks[item] for item in answer.chunk_ids])
            if not correct_text.strip():
                raise MissionContractError("sentence-building answer cannot be empty")
        if question.interaction == "markerChoice":
            marker_facts = list(question.marker_fact_ids.values())
            if any(fact_id not in objects_by_fact for fact_id in marker_facts):
                raise MissionContractError("marker choices must map to object facts")
            if len(marker_facts) != len(set(marker_facts)):
                raise MissionContractError("marker choices must map to distinct objects")
            correct_fact = question.marker_fact_ids[answer.correct_option_id]
            if correct_fact not in question.fact_ids:
                raise MissionContractError("correct marker object must be in the question facts")

        for fact_ref in question.fact_ids:
            if facts[fact_ref] != "object":
                continue
            terms = terms_by_fact.get(fact_ref, [])
            if slot.purpose in {"confirmName", "chooseAttribute", "followUpSceneFact"}:
                continue
            if not terms or any(
                _fold_contract_text(term.target_text) not in _fold_contract_text(correct_text)
                for term in terms
            ):
                raise MissionContractError(
                    "correct answer must contain every approved object term"
                )
        question_objects = set(question.fact_ids) & object_fact_ids
        if not question_objects:
            raise MissionContractError(
                f"question {index} must reference its focus object fact"
            )
        if "describe-colour" in slot.target_ids:
            colour_focus_indices.add(slot.focus)
            colour_objects = {
                approved_colour_fact_objects[fact_ref]
                for fact_ref in question.fact_ids
                if fact_ref in approved_colour_fact_objects
            }
            question_objects.intersection_update(colour_objects)
            if not question_objects:
                raise MissionContractError(
                    f"question {index} targeting describe-colour must reference an "
                    "approved colour attribute fact for its focus object"
                )
        if slot.focus in focus_candidates:
            focus_candidates[slot.focus].intersection_update(question_objects)
            if not focus_candidates[slot.focus]:
                if slot.focus in colour_focus_indices:
                    raise MissionContractError(
                        f"question {index} targeting describe-colour must reference an "
                        "approved colour attribute fact for its focus object"
                    )
                raise MissionContractError(
                    "questions with the same focus must share one object fact"
                )
        else:
            focus_candidates[slot.focus] = question_objects

    if any(not candidates for candidates in focus_candidates.values()):
        raise MissionContractError("questions with the same focus must share one object fact")
    focus_indices = sorted(focus_candidates)
    object_order = {
        item.fact_id: index for index, item in enumerate(contract.scene_facts.objects)
    }

    def has_distinct_focus_objects(position: int, used: set[str]) -> bool:
        if position == len(focus_indices):
            return True
        candidates = sorted(
            focus_candidates[focus_indices[position]],
            key=object_order.__getitem__,
        )
        return any(
            candidate not in used
            and has_distinct_focus_objects(position + 1, {*used, candidate})
            for candidate in candidates
        )

    if not has_distinct_focus_objects(0, set()):
        raise MissionContractError("different focus indices must use different objects")

    for required in definition.expected_performance.required_target_groups:
        if not set(required) & covered_targets:
            raise MissionContractError("output does not cover every required target group")
    if plan.min_connected_facts is not None:
        connected_questions = []
        prior_connect_facts: set[str] = set()
        for question in output.questions:
            if "connect-scene-facts" in question.target_ids:
                if len(set(question.fact_ids)) < plan.min_connected_facts:
                    raise MissionContractError(
                        "A2 connect questions need more distinct scene facts"
                    )
                connected_questions.append(question)
                prior_connect_facts.update(question.fact_ids)
            if "follow-up-scene-fact" in question.target_ids and (
                not connected_questions or not set(question.fact_ids) <= prior_connect_facts
            ):
                raise MissionContractError(
                    "follow-up questions must use facts from a preceding connect question"
                )
        if not connected_questions:
            raise MissionContractError("A2 requires a connect-scene-facts question")


__all__ = [
    "CONTRACT_VERSION",
    "M01_VARIANTS",
    "M01LevelPlan",
    "M01Variant",
    "MissionContractError",
    "convert_generated_lesson",
    "UnroutedMissionVariant",
    "default_join",
    "fact_id",
    "generation_enabled",
    "join_chunks",
    "load_m01_level_plan",
    "m01_variant",
    "validate_contract_input",
    "validate_contract_output",
]
