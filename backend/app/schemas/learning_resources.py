"""Curated, versioned reference content for mission concepts and writing systems."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, LanguageCode, NonEmptyText
from app.schemas.enums import ProficiencyLevel
from app.schemas.tasks import ContentVersion, ContractId, MissionId


class CheatSheetExample(ApiModel):
    target_text: NonEmptyText
    translation: NonEmptyText
    note: NonEmptyText | None = None


class CheatSheetConcept(ApiModel):
    """One teachable idea, linked to a target or pattern in the mission contract."""

    concept_id: ContractId
    title: NonEmptyText
    explanation: NonEmptyText
    formula: NonEmptyText | None = None
    examples: Annotated[list[CheatSheetExample], Field(min_length=1)]
    tips: list[NonEmptyText] = Field(default_factory=list)
    character_reference_section_ids: list[ContractId] = Field(default_factory=list)


class MissionCheatSheet(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    language_code: LanguageCode
    title: NonEmptyText
    summary: NonEmptyText
    concepts: Annotated[list[CheatSheetConcept], Field(min_length=1)]
    character_reference_id: ContractId | None = None
    character_reference_version: ContentVersion | None = None

    @model_validator(mode="after")
    def validate_unique_concepts(self) -> MissionCheatSheet:
        concept_ids = [concept.concept_id for concept in self.concepts]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("conceptIds cannot repeat")
        reference_values = (self.character_reference_id, self.character_reference_version)
        if None in reference_values and any(value is not None for value in reference_values):
            raise ValueError(
                "characterReferenceId and characterReferenceVersion must be set together"
            )
        return self

    @property
    def key(self) -> tuple[str, ProficiencyLevel, int, str]:
        return (
            self.mission_id,
            self.practice_level,
            self.content_version,
            self.language_code.casefold(),
        )


class MissionCheatSheetSummary(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    language_code: LanguageCode
    title: NonEmptyText
    summary: NonEmptyText
    character_reference_id: ContractId | None = None
    character_reference_version: ContentVersion | None = None


class CharacterEntry(ApiModel):
    character: NonEmptyText
    name: NonEmptyText
    pronunciation: NonEmptyText | None = None
    example: NonEmptyText | None = None
    example_translation: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_example_translation(self) -> CharacterEntry:
        if self.example_translation is not None and self.example is None:
            raise ValueError("exampleTranslation requires example")
        return self


class CharacterReferenceSection(ApiModel):
    section_id: ContractId
    title: NonEmptyText
    explanation: NonEmptyText
    characters: list[CharacterEntry] = Field(default_factory=list)
    examples: list[CheatSheetExample] = Field(default_factory=list)


class CharacterReference(ApiModel):
    reference_id: ContractId
    language_code: LanguageCode
    content_version: ContentVersion
    script_name: NonEmptyText
    title: NonEmptyText
    introduction: NonEmptyText
    sections: Annotated[list[CharacterReferenceSection], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_sections(self) -> CharacterReference:
        section_ids = [section.section_id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("sectionIds cannot repeat")
        return self


class CharacterReferenceSummary(ApiModel):
    reference_id: ContractId
    language_code: LanguageCode
    content_version: ContentVersion
    script_name: NonEmptyText
    title: NonEmptyText
