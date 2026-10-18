"""Routing and contract validation for the staged multilingual M01 path."""

from __future__ import annotations

import logging
import os
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.languages import get_language, languages
from app.missions import get_mission
from app.schemas.base import ApiModel, NonEmptyText
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
type M01Realised = Literal["focusObject", "focusColour", "details", "oneDetail"]


class M01QuestionSlot(ApiModel):
    purpose: str
    section: NonEmptyText
    target_ids: list[str] = Field(min_length=1)
    interaction: M01Interaction
    evidence: EvidenceType
    criteria: list[str] = Field(min_length=1)
    focus: Annotated[int, Field(ge=1)]
    options: tuple[Annotated[int, Field(ge=2)], Annotated[int, Field(ge=2)]] | None = None
    distractor_chunks: tuple[
        Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]
    ] | None = None
    # Yes/no slots: the statement names the focus object or another confirmed object.
    yes_no: bool = False
    # Facts whose approved terms the correct answer must realise.
    realises: list[M01Realised] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> M01QuestionSlot:
        if self.yes_no and (self.interaction != "multipleChoice" or self.options != (2, 2)):
            raise ValueError("yes/no slots are two-option multipleChoice questions")
        if self.interaction == "markerChoice" and (self.yes_no or self.realises):
            raise ValueError("markerChoice slots are checked by their marker mapping only")
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
    title: NonEmptyText
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


def _english_section_label(source_text: str) -> str:
    label = re.sub(r"^(?:a|an|the)\s+", "", source_text.strip(), flags=re.IGNORECASE)
    return label.casefold().capitalize()


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
                raise MissionContractError(
                    f"{_question_label(index + 1, question, plan)}: unknown target: {target_id}"
                )

        section = slot.section
        if "{label}" in section:
            focus_fact = next(
                (fact_ref for fact_ref in question.fact_ids if fact_ref in objects),
                None,
            )
            if focus_fact is None:
                raise MissionContractError(
                    f"{_question_label(index + 1, question, plan)}: no focus object "
                    "for its section label"
                )
            source_term = next(iter(terms_by_fact.get(focus_fact, [])), None)
            if source_term is None:
                raise MissionContractError(
                    f"{_question_label(index + 1, question, plan)}: focus object "
                    "has no approved English source term for its section label"
                )
            section = section.format(label=_english_section_label(source_term.source_text))

        questions.append({
            "question_id": question.question_id,
            "target_ids": question.target_ids,
            "section": section,
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
            "statement_fact_id": question.statement_fact_id,
            "prompt_term_uses": question.prompt_term_uses,
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
        title=plan.title,
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


def _question_label(index: int, question, plan: M01LevelPlan | None) -> str:
    purpose = (
        plan.questions[index - 1].purpose
        if plan is not None and index <= len(plan.questions) else "unplanned"
    )
    return f"question {index} ({question.question_id}, slot {purpose})"


def expected_preparation_cards(plan: M01LevelPlan, contract: M01ContractInput) -> int:
    """The exact card count: one per confirmed object when per-object, plus the extras."""
    per_object = len(contract.scene_facts.objects) if plan.preparation.per_object else 0
    return per_object + plan.preparation.extra_cards


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

    label_plan = plan or load_m01_level_plan(contract.mission.practice_level)
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
    for index, question in enumerate(output.questions, start=1):
        label = _question_label(index, question, label_plan)
        unknown_targets = set(question.target_ids) - target_ids
        if unknown_targets:
            raise MissionContractError(
                f"{label}: question targets do not belong to this mission: "
                f"{sorted(unknown_targets)}"
            )
        covered_targets.update(question.target_ids)
        _check_fact_references(question.fact_ids, valid_fact_ids, f"{label}: question")

        option_ids = [option.option_id for option in question.options]
        if len(option_ids) != len(set(option_ids)):
            raise MissionContractError(f"{label}: question option IDs must be unique")
        chunk_ids = [chunk.chunk_id for chunk in question.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise MissionContractError(f"{label}: chunk IDs must be unique per question")

        if question.interaction == "markerChoice":
            if question.marker_fact_ids is None:
                raise MissionContractError(
                    f"{label}: markerChoice questions require marker facts"
                )
            if set(question.marker_fact_ids) != set(option_ids):
                raise MissionContractError(
                    f"{label}: marker facts must cover exactly the offered options "
                    f"{sorted(option_ids)}, got {sorted(question.marker_fact_ids)}"
                )
            _check_fact_references(
                list(question.marker_fact_ids.values()), valid_fact_ids,
                f"{label}: marker choice",
            )
            for fact_ref in question.marker_fact_ids.values():
                object_fact = object_facts.get(fact_ref)
                if object_fact is None:
                    raise MissionContractError(
                        f"{label}: marker choices must map to object facts, got {fact_ref}"
                    )
                if object_fact.marker is None:
                    raise MissionContractError(
                        f"{label}: marker choice objects must have review markers "
                        f"({fact_ref} has none)"
                    )
        elif question.marker_fact_ids is not None:
            raise MissionContractError(
                f"{label}: marker facts are only valid for markerChoice questions"
            )

    for group in definition.expected_performance.required_target_groups:
        if not set(group) & covered_targets:
            raise MissionContractError("output does not cover every required target group")

    answers = output.private.answers
    if set(answers) != set(question_ids):
        raise MissionContractError("every question must have exactly one private answer")
    for index, question in enumerate(output.questions, start=1):
        label = _question_label(index, question, label_plan)
        answer = answers[question.question_id]
        option_ids = [option.option_id for option in question.options]
        if question.interaction in {"multipleChoice", "markerChoice"}:
            if answer.correct_option_id not in option_ids:
                raise MissionContractError(
                    f"{label}: private answer must be one of the offered options "
                    f"{option_ids}, got {answer.correct_option_id!r}"
                )
        if question.interaction == "sentenceBuilding":
            if not answer.chunk_ids:
                raise MissionContractError(
                    f"{label}: sentence-building answers need ordered chunk IDs"
                )
            if len(answer.chunk_ids) != len(set(answer.chunk_ids)):
                raise MissionContractError(
                    f"{label}: sentence-building answer chunk IDs cannot repeat"
                )
            if not set(answer.chunk_ids) <= {chunk.chunk_id for chunk in question.chunks}:
                raise MissionContractError(
                    f"{label}: sentence-building answers must use offered question chunks"
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

    preparation_plan = label_plan
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
        if missing := assessed_objects - taught_objects:
            raise MissionContractError(
                "preparation cards must teach every assessed object before assessment; "
                f"untaught: {sorted(missing)}"
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


def _inflects(term: str, surface: str) -> bool:
    """Conservative, language-agnostic test that folded ``surface`` is a form of ``term``.

    Word by word, the surface either extends the term (a suffix) or keeps at least
    half of a term word longer than three characters, and at least two characters,
    replacing at most its final two characters before a non-empty ending.
    """
    term_words, surface_words = term.split(), surface.split()
    if not term_words or len(term_words) != len(surface_words):
        return False
    for term_word, surface_word in zip(term_words, surface_words, strict=True):
        if surface_word.startswith(term_word):
            continue
        stem = len(os.path.commonprefix([term_word, surface_word]))
        if (
            len(term_word) <= 3
            or stem < max(2, (len(term_word) + 1) // 2)
            or len(term_word) - stem > 2
            or len(surface_word) <= stem
        ):
            return False
    return True


@dataclass(frozen=True)
class _PlannedQuestion:
    index: int
    question: object
    slot: M01QuestionSlot

    def error(self, message: str) -> MissionContractError:
        return MissionContractError(
            f"question {self.index} ({self.question.question_id}, "
            f"slot {self.slot.purpose}): {message}"
        )


def _realised_terms(item: _PlannedQuestion, where, text, term_uses, terms_by_id) -> set[str]:
    """Term IDs ``text`` realises: verbatim approved text, or a checked declared form."""
    folded = _fold_contract_text(text)
    realised = {
        term_id
        for term_id, term in terms_by_id.items()
        if _fold_contract_text(term.target_text) in folded
    }
    for use in term_uses:
        term = terms_by_id.get(use.term_id)
        if term is None:
            raise item.error(f"{where} declares unknown term {use.term_id!r}")
        surface = _fold_contract_text(use.surface)
        approved = _fold_contract_text(term.target_text)
        if surface not in folded:
            raise item.error(
                f"{where} declares surface {use.surface!r} for {use.term_id!r}, "
                f"but its text is {text!r}"
            )
        if approved not in surface and not _inflects(approved, surface):
            raise item.error(
                f"{where} surface {use.surface!r} is not a recognised form of approved "
                f"term {term.target_text!r} ({use.term_id})"
            )
        realised.add(use.term_id)
    return realised


def _require_fact(item, realised, fact_ref, role, terms_by_fact, text, where="correct answer"):
    terms = terms_by_fact.get(fact_ref, [])
    if not terms:
        raise item.error(f"{role} {fact_ref} has no approved term")
    if not realised & {term.term_id for term in terms}:
        expected = " or ".join(repr(term.target_text) for term in terms)
        raise item.error(
            f"{where} {text!r} does not realise the {role} {fact_ref}: expected approved "
            f"term {expected} or a declared form of it"
        )


def _validate_answer_rule(
    item, focus, answer, facts, objects_by_fact, terms_by_fact, terms_by_id,
    colour_fact_objects,
) -> None:
    """Check the correct answer against the slot's interaction-specific rule."""
    question, slot = item.question, item.slot
    option_terms = {
        option.option_id: _realised_terms(
            item, f"option {option.option_id}", option.label, option.term_uses, terms_by_id
        )
        for option in question.options
    }
    chunk_terms = {
        chunk.chunk_id: _realised_terms(
            item, f"chunk {chunk.chunk_id}", chunk.text, chunk.term_uses, terms_by_id
        )
        for chunk in question.chunks
    }
    if question.interaction == "markerChoice":
        correct_fact = question.marker_fact_ids[answer.correct_option_id]
        if correct_fact != focus:
            raise item.error(
                f"correct marker option {answer.correct_option_id} maps to {correct_fact}, "
                f"expected the focus object {focus}"
            )
        return

    if slot.yes_no:
        meanings = [option.meaning for option in question.options]
        if sorted(str(meaning) for meaning in meanings) != ["no", "yes"]:
            raise item.error(
                f"yes/no options must be one 'yes' and one 'no', got meanings {meanings}"
            )
        statement = question.statement_fact_id
        if statement is None:
            raise item.error("yes/no questions must name the stated object in statementFactId")
        if statement not in objects_by_fact:
            raise item.error(f"statementFactId {statement} is not a confirmed object fact")
        if statement not in question.fact_ids:
            raise item.error(f"statementFactId {statement} must be listed in factIds")
        prompt_terms = _realised_terms(
            item, "prompt", question.prompt, question.prompt_term_uses, terms_by_id
        )
        _require_fact(
            item, prompt_terms, statement, "stated object", terms_by_fact, question.prompt,
            where="prompt",
        )
        truth = statement == focus
        expected = "yes" if truth else "no"
        correct = next(
            option for option in question.options
            if option.option_id == answer.correct_option_id
        )
        if correct.meaning != expected:
            reason = (
                "the statement names the focus object" if truth
                else f"the statement names {statement}, not the focus object {focus}"
            )
            raise item.error(
                f"correct option {correct.option_id} means {correct.meaning!r}, "
                f"expected {expected!r} because {reason}"
            )
        return

    if question.interaction == "sentenceBuilding":
        chunks = {chunk.chunk_id: chunk for chunk in question.chunks}
        answer_text = join_chunks([chunks[chunk_id] for chunk_id in answer.chunk_ids])
        realised = _realised_terms(item, "correct answer", answer_text, [], terms_by_id)
        for chunk_id in answer.chunk_ids:
            realised |= chunk_terms[chunk_id]
    else:
        answer_text = next(
            option.label for option in question.options
            if option.option_id == answer.correct_option_id
        )
        realised = option_terms[answer.correct_option_id]

    details = [
        fact_ref for fact_ref in question.fact_ids
        if facts[fact_ref] in {"attribute", "relation"}
    ]
    for rule in slot.realises:
        if rule == "focusObject":
            _require_fact(item, realised, focus, "focus object", terms_by_fact, answer_text)
        elif rule == "focusColour":
            colour = next(
                (
                    fact_ref for fact_ref in question.fact_ids
                    if colour_fact_objects.get(fact_ref) == focus
                ),
                None,
            )
            if colour is None:
                raise item.error(
                    f"must list an approved colour fact for the focus object {focus}"
                )
            _require_fact(
                item, realised, colour, "focus object's colour", terms_by_fact, answer_text
            )
        elif not details:
            raise item.error("must list the attribute or relation facts it asks about")
        elif rule == "details":
            for fact_ref in details:
                _require_fact(item, realised, fact_ref, "detail fact", terms_by_fact, answer_text)
        else:
            for fact_ref in details:
                if not terms_by_fact.get(fact_ref):
                    raise item.error(f"detail fact {fact_ref} has no approved term")
            if not any(
                realised & {term.term_id for term in terms_by_fact[fact_ref]}
                for fact_ref in details
            ):
                expected = " or ".join(
                    repr(term.target_text)
                    for fact_ref in details for term in terms_by_fact[fact_ref]
                )
                raise item.error(
                    f"correct answer {answer_text!r} realises none of the listed detail "
                    f"facts {details}: expected one of {expected} or a declared form"
                )


def _validate_planned_output(contract, definition, output, plan) -> None:
    if output.mission.content_version != plan.content_version:
        raise MissionContractError("plan content version does not match the mission")
    expected_questions = len(plan.questions)
    if len(output.questions) != expected_questions:
        raise MissionContractError(
            f"question count {len(output.questions)} does not match plan {expected_questions}"
        )
    expected_preparation = expected_preparation_cards(plan, contract)
    if len(output.preparation) != expected_preparation:
        basis = (
            f"one per confirmed object ({len(contract.scene_facts.objects)}) plus "
            f"{plan.preparation.extra_cards} extra"
            if plan.preparation.per_object
            else f"{plan.preparation.extra_cards} extra, none per object"
        )
        raise MissionContractError(
            f"preparation-card count {len(output.preparation)} is outside "
            f"{expected_preparation}–{expected_preparation} ({basis})"
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
    terms_by_id = {term.term_id: term for term in contract.vocabulary}
    approved_colour_fact_objects = {
        item.fact_id: item.object_fact_id
        for item in contract.scene_facts.attributes
        if item.kind == "colour" and item.fact_id in terms_by_fact
    }
    allowed_kinds = set(plan.fact_kinds)

    references = [
        *((f"preparation card {card.card_id}", card.fact_ids) for card in output.preparation),
        *(
            (_question_label(index, question, plan), question.fact_ids)
            for index, question in enumerate(output.questions, start=1)
        ),
    ]
    for source, fact_ids in references:
        outside = [fact_ref for fact_ref in fact_ids if facts[fact_ref] not in allowed_kinds]
        if outside:
            raise MissionContractError(
                f"{source} references a fact kind outside the plan: {outside} "
                f"(allowed kinds {sorted(allowed_kinds)})"
            )

    covered_targets: set[str] = set()
    focus_candidates: dict[int, set[str]] = {}
    colour_focus_indices: set[int] = set()
    planned: list[_PlannedQuestion] = []
    for index, (question, slot) in enumerate(
        zip(output.questions, plan.questions, strict=True), start=1,
    ):
        item = _PlannedQuestion(index, question, slot)
        planned.append(item)
        if question.target_ids != slot.target_ids:
            raise item.error(
                f"targets {question.target_ids} do not match plan slot targets "
                f"{slot.target_ids}"
            )
        if question.interaction != slot.interaction:
            raise item.error(
                f"interaction {question.interaction} does not match plan slot "
                f"interaction {slot.interaction}"
            )
        covered_targets.update(question.target_ids)
        choice = question.interaction in {"multipleChoice", "markerChoice"}
        if choice:
            if question.chunks:
                raise item.error("choice questions cannot have chunks")
            minimum, maximum = slot.options
            if not minimum <= len(question.options) <= maximum:
                raise item.error(
                    f"option count {len(question.options)} is outside "
                    f"{minimum}–{maximum} for {slot.purpose}"
                )
            labels = [_fold_contract_text(option.label) for option in question.options]
            if len(labels) != len(set(labels)):
                raise item.error("choice labels must be distinct")
        elif question.options:
            raise item.error("sentenceBuilding questions cannot have options")
        if not slot.yes_no:
            if question.statement_fact_id is not None:
                raise item.error("only yes/no slots name a statementFactId")
            if any(option.meaning is not None for option in question.options):
                raise item.error("only yes/no options carry a yes/no meaning")

        answer = output.private.answers[question.question_id]
        if not choice:
            if len(answer.chunk_ids) > plan.max_answer_chunks:
                raise item.error(
                    f"answer uses {len(answer.chunk_ids)} chunks, more than the plan's "
                    f"{plan.max_answer_chunks}"
                )
            distractors = len(question.chunks) - len(answer.chunk_ids)
            minimum, maximum = slot.distractor_chunks
            if not minimum <= distractors <= maximum:
                raise item.error(
                    f"distractor-chunk count {distractors} is outside "
                    f"{minimum}–{maximum} for {slot.purpose}"
                )
            if any(not chunk.text.strip() for chunk in question.chunks):
                raise item.error("sentence chunks must contain text")
            chunks = {chunk.chunk_id: chunk for chunk in question.chunks}
            if not join_chunks([chunks[chunk_id] for chunk_id in answer.chunk_ids]).strip():
                raise item.error("sentence-building answer cannot be empty")

        question_objects = [
            fact_ref for fact_ref in question.fact_ids if fact_ref in object_fact_ids
        ]
        if not question_objects:
            raise item.error("must reference its focus object fact")
        if question.interaction == "markerChoice":
            marker_facts = list(question.marker_fact_ids.values())
            if len(marker_facts) != len(set(marker_facts)):
                raise item.error("marker choices must map to distinct objects")
            correct_fact = question.marker_fact_ids[answer.correct_option_id]
            if correct_fact not in question.fact_ids:
                raise item.error(
                    f"correct marker object {correct_fact} must be in the question facts"
                )
            candidates = {correct_fact}
        elif slot.yes_no:
            # The first listed object is the one the lesson highlights.
            candidates = {question_objects[0]}
        else:
            candidates = set(question_objects)
        if "describe-colour" in slot.target_ids:
            colour_focus_indices.add(slot.focus)
            colour_objects = {
                approved_colour_fact_objects[fact_ref]
                for fact_ref in question.fact_ids
                if fact_ref in approved_colour_fact_objects
            }
            candidates &= colour_objects
            if not candidates:
                raise item.error(
                    "targeting describe-colour must reference an approved colour attribute "
                    "fact for its focus object"
                )
        if slot.focus in focus_candidates:
            shared = focus_candidates[slot.focus] & candidates
            if not shared:
                if slot.focus in colour_focus_indices:
                    raise item.error(
                        "targeting describe-colour must reference an approved colour "
                        "attribute fact for its focus object"
                    )
                raise item.error(
                    f"questions with the same focus must share one object fact: focus "
                    f"{slot.focus} candidates {sorted(candidates)} do not overlap "
                    f"{sorted(focus_candidates[slot.focus])}"
                )
            focus_candidates[slot.focus] = shared
        else:
            focus_candidates[slot.focus] = candidates

    focus_indices = sorted(focus_candidates)
    object_order = {
        item.fact_id: index for index, item in enumerate(contract.scene_facts.objects)
    }

    def assign_focus_objects(position: int, used: set[str]) -> dict[int, str] | None:
        if position == len(focus_indices):
            return {}
        focus_index = focus_indices[position]
        for candidate in sorted(focus_candidates[focus_index], key=object_order.__getitem__):
            if candidate in used:
                continue
            rest = assign_focus_objects(position + 1, {*used, candidate})
            if rest is not None:
                return {focus_index: candidate, **rest}
        return None

    focus_objects = assign_focus_objects(0, set())
    if focus_objects is None:
        raise MissionContractError(
            "different focus indices must use different objects: candidates "
            f"{ {index: sorted(focus_candidates[index]) for index in focus_indices} }"
        )

    for required in definition.expected_performance.required_target_groups:
        if not set(required) & covered_targets:
            raise MissionContractError("output does not cover every required target group")

    if plan.min_connected_facts is not None:
        connected_questions = []
        prior_connect_facts: set[str] = set()
        for item in planned:
            question = item.question
            if "connect-scene-facts" in question.target_ids:
                distinct = len(set(question.fact_ids))
                if distinct < plan.min_connected_facts:
                    raise item.error(
                        f"A2 connect questions need more distinct scene facts: {distinct} "
                        f"listed, expected at least {plan.min_connected_facts}"
                    )
                connected_questions.append(question)
                prior_connect_facts.update(question.fact_ids)
            if "follow-up-scene-fact" in question.target_ids and (
                not connected_questions or not set(question.fact_ids) <= prior_connect_facts
            ):
                raise item.error(
                    "follow-up questions must use facts from a preceding connect question; "
                    f"unused: {sorted(set(question.fact_ids) - prior_connect_facts)}"
                )
        if not connected_questions:
            raise MissionContractError("A2 requires a connect-scene-facts question")

    for item in planned:
        _validate_answer_rule(
            item,
            focus_objects[item.slot.focus],
            output.private.answers[item.question.question_id],
            facts,
            objects_by_fact,
            terms_by_fact,
            terms_by_id,
            approved_colour_fact_objects,
        )


__all__ = [
    "CONTRACT_VERSION",
    "M01_VARIANTS",
    "M01LevelPlan",
    "M01Variant",
    "MissionContractError",
    "convert_generated_lesson",
    "expected_preparation_cards",
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
