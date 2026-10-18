"""Routing and contract validation for the staged multilingual M01 path."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from app.languages import get_language
from app.missions import get_mission
from app.schemas.enums import ProficiencyLevel
from app.schemas.languages import Language
from app.schemas.mission_m01_contract import (
    M01ContractInput,
    M01ContractOutput,
    SentenceChunk,
    fact_id,
)
from app.schemas.missions import MissionDefinition
from app.schemas.tasks import QuestionEvaluation

CONTRACT_VERSION = "m01-multilingual.v1"
MULTILINGUAL_M01_ENABLED = False

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


class UnroutedMissionVariant(LookupError):
    """A mission level/version without an explicit route."""


class MissionContractError(ValueError):
    """A multilingual M01 input or output violates the contract."""


def m01_variant(
    mission_id: str, level: ProficiencyLevel | str, version: int
) -> M01Variant:
    key = mission_id, str(level), version
    try:
        return M01_VARIANTS[key]
    except KeyError:
        raise UnroutedMissionVariant(f"no multilingual M01 route for {key}") from None


def generation_enabled() -> bool:
    return MULTILINGUAL_M01_ENABLED


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
    contract: M01ContractInput, output: M01ContractOutput
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
    for card in output.preparation:
        _check_fact_references(card.fact_ids, valid_fact_ids, "preparation card")
    for example in output.worked_examples:
        _check_fact_references(example.fact_ids, valid_fact_ids, "worked example")

    target_ids = set(definition.targets)
    question_ids = [question.question_id for question in output.questions]
    if len(question_ids) != len(set(question_ids)):
        raise MissionContractError("question IDs must be unique")
    if len(output.questions) < definition.expected_performance.min_assessed_questions:
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
        elif question.marker_fact_ids is not None:
            raise MissionContractError("marker facts are only valid for markerChoice questions")

        hint_levels = [hint.level for hint in question.hints]
        if hint_levels != sorted(set(hint_levels)):
            raise MissionContractError("hint levels must be strictly ascending")
        if any(hint.reveals_answer for hint in question.hints[:-1]):
            raise MissionContractError("only the final hint may reveal the answer")

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


__all__ = [
    "CONTRACT_VERSION",
    "M01_VARIANTS",
    "MULTILINGUAL_M01_ENABLED",
    "M01Variant",
    "MissionContractError",
    "UnroutedMissionVariant",
    "default_join",
    "fact_id",
    "generation_enabled",
    "join_chunks",
    "m01_variant",
    "validate_contract_input",
    "validate_contract_output",
]
