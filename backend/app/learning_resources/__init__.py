"""Load and validate curated mission cheatsheets and character references."""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

from pydantic import ValidationError

from app.missions import get_mission
from app.schemas.enums import ProficiencyLevel
from app.schemas.learning_resources import CharacterReference, MissionCheatSheet

CONTENT_DIR = Path(__file__).parent / "content"
CHEAT_SHEETS_DIR = CONTENT_DIR / "cheatsheets"
CHARACTER_REFERENCES_DIR = CONTENT_DIR / "character-references"


class LearningResourceConfigurationError(ValueError):
    pass


def _version_suffix(content_version: int) -> str:
    return "" if content_version == 1 else f"-{content_version}"


def cheat_sheet_file_name(cheat_sheet: MissionCheatSheet) -> str:
    return (
        f"{cheat_sheet.mission_id}-{cheat_sheet.practice_level}"
        f"{_version_suffix(cheat_sheet.content_version)}.toml"
    )


def character_reference_file_name(reference: CharacterReference) -> str:
    return f"{reference.reference_id}{_version_suffix(reference.content_version)}.toml"


def _read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise LearningResourceConfigurationError(
            f"Invalid learning resource {path.name}: {exc}"
        ) from None


def load_character_reference_file(path: Path) -> CharacterReference:
    try:
        reference = CharacterReference.model_validate(_read_toml(path))
    except ValidationError as exc:
        raise LearningResourceConfigurationError(
            f"Invalid character reference {path.name}: {exc}"
        ) from None
    expected_path = Path(reference.language_code.casefold()) / character_reference_file_name(
        reference
    )
    if Path(path.parent.name) / path.name != expected_path:
        raise LearningResourceConfigurationError(
            f"{path} must end with {expected_path}"
        )
    return reference


def load_character_references(directory: Path) -> dict[tuple[str, int], CharacterReference]:
    references: dict[tuple[str, int], CharacterReference] = {}
    for path in sorted(directory.glob("*/*.toml")):
        reference = load_character_reference_file(path)
        key = (reference.reference_id, reference.content_version)
        if key in references:
            raise LearningResourceConfigurationError(
                f"duplicate character reference {key}"
            )
        references[key] = reference
    return references


def load_cheat_sheet_file(
    path: Path, references: dict[tuple[str, int], CharacterReference]
) -> MissionCheatSheet:
    try:
        cheat_sheet = MissionCheatSheet.model_validate(_read_toml(path))
    except ValidationError as exc:
        raise LearningResourceConfigurationError(
            f"Invalid mission cheatsheet {path.name}: {exc}"
        ) from None

    expected_path = Path(cheat_sheet.language_code.casefold()) / cheat_sheet_file_name(
        cheat_sheet
    )
    if Path(path.parent.name) / path.name != expected_path:
        raise LearningResourceConfigurationError(
            f"{path} must end with {expected_path}"
        )

    mission = get_mission(
        cheat_sheet.mission_id,
        cheat_sheet.practice_level,
        cheat_sheet.content_version,
    )
    if mission is None:
        raise LearningResourceConfigurationError(
            f"{path.name} references an unknown mission version"
        )
    valid_concepts = {
        *(target.target_id for target in mission.objective.targets),
        *(pattern.pattern_id for pattern in mission.language_patterns),
    }
    unknown_concepts = sorted(
        concept.concept_id
        for concept in cheat_sheet.concepts
        if concept.concept_id not in valid_concepts
    )
    if unknown_concepts:
        raise LearningResourceConfigurationError(
            f"{path.name} references unknown mission concepts: {', '.join(unknown_concepts)}"
        )

    referenced_sections = {
        section_id
        for concept in cheat_sheet.concepts
        for section_id in concept.character_reference_section_ids
    }
    if cheat_sheet.character_reference_id is None:
        if referenced_sections:
            raise LearningResourceConfigurationError(
                f"{path.name} links character sections without characterReferenceId"
            )
        return cheat_sheet

    reference_key = (
        cheat_sheet.character_reference_id,
        cheat_sheet.character_reference_version,
    )
    reference = references.get(reference_key)
    if reference is None:
        raise LearningResourceConfigurationError(
            f"{path.name} references unknown character reference "
            f"{cheat_sheet.character_reference_id}"
        )
    if reference.language_code.casefold() != cheat_sheet.language_code.casefold():
        raise LearningResourceConfigurationError(
            f"{path.name} and its character reference use different languages"
        )
    valid_sections = {section.section_id for section in reference.sections}
    if unknown_sections := sorted(referenced_sections - valid_sections):
        raise LearningResourceConfigurationError(
            f"{path.name} references unknown character sections: {', '.join(unknown_sections)}"
        )
    return cheat_sheet


def load_cheat_sheets(
    directory: Path, references: dict[tuple[str, int], CharacterReference]
) -> dict[tuple[str, ProficiencyLevel, int, str], MissionCheatSheet]:
    cheat_sheets: dict[tuple[str, ProficiencyLevel, int, str], MissionCheatSheet] = {}
    for path in sorted(directory.glob("*/*.toml")):
        cheat_sheet = load_cheat_sheet_file(path, references)
        if cheat_sheet.key in cheat_sheets:
            raise LearningResourceConfigurationError(
                f"duplicate mission cheatsheet {cheat_sheet.key}"
            )
        cheat_sheets[cheat_sheet.key] = cheat_sheet
    return cheat_sheets


@cache
def character_references() -> dict[tuple[str, int], CharacterReference]:
    return load_character_references(CHARACTER_REFERENCES_DIR)


@cache
def mission_cheat_sheets() -> dict[
    tuple[str, ProficiencyLevel, int, str], MissionCheatSheet
]:
    return load_cheat_sheets(CHEAT_SHEETS_DIR, character_references())


def get_mission_cheat_sheet(
    mission_id: str,
    practice_level: ProficiencyLevel | str,
    content_version: int,
    language_code: str,
) -> MissionCheatSheet | None:
    return mission_cheat_sheets().get(
        (
            mission_id,
            ProficiencyLevel(practice_level),
            content_version,
            language_code.casefold(),
        )
    )


def get_character_reference(
    reference_id: str, content_version: int
) -> CharacterReference | None:
    return character_references().get((reference_id, content_version))
