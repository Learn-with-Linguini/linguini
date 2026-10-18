"""Generation definition for the shared multilingual M01 lesson."""

from typing import Any

from app.ai.features.learning_tasks.m01_multilingual_prompt import (
    M01_MULTILINGUAL_PROMPT_VERSION,
    M01_MULTILINGUAL_REPAIR_INSTRUCTION,
    M01_MULTILINGUAL_SCHEMA_VERSION,
    M01_MULTILINGUAL_SYSTEM_PROMPT,
)
from app.ai.features.learning_tasks.mission import MissionGeneration
from app.missions.m01_multilingual import (
    CONTRACT_VERSION,
    MissionContractError,
    convert_generated_lesson,
    load_m01_level_plan,
    validate_contract_output,
)
from app.schemas.mission_m01_contract import M01ContractInput, M01GeneratedLesson


def _validate(payload: dict[str, Any], result: M01GeneratedLesson):
    contract = M01ContractInput.model_validate(payload["contract"])
    output = convert_generated_lesson(contract, result)
    validate_contract_output(
        contract,
        output,
        load_m01_level_plan(contract.mission.practice_level),
    )
    return output


def _fallback(_payload):
    raise MissionContractError("multilingual M01 generation has no deterministic fallback")


M01_MULTILINGUAL_GENERATION = MissionGeneration(
    prompt_version=M01_MULTILINGUAL_PROMPT_VERSION,
    schema_version=M01_MULTILINGUAL_SCHEMA_VERSION,
    validator_version=f"{CONTRACT_VERSION}:plan-aware-v5",
    system_prompt=M01_MULTILINGUAL_SYSTEM_PROMPT,
    result_model=M01GeneratedLesson,
    validate=_validate,
    fallback=_fallback,
    json_schema_name="m01_multilingual_v1",
    repair_instruction=M01_MULTILINGUAL_REPAIR_INSTRUCTION,
)
