"""Strict language-pack data contracts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import Field, PrivateAttr, StringConstraints, field_validator, model_validator

from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import ProficiencyLevel
from app.schemas.tasks import ContentVersion, ContractId, MissionId

type ScriptCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][a-z]{3}$")]
type LanguageTag = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=63,
        pattern=(
            r"^(?:[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*|"
            r"[A-Za-z]{4,8}(?:-[A-Za-z0-9]{1,8})*|"
            r"x(?:-[A-Za-z0-9]{1,8})+)$"
        ),
    ),
]
type TextDirection = Literal["ltr", "rtl"]
type WordSeparator = Literal["space", "none"]
type ChunkJoin = Literal["space", "none"]
type ReviewStatus = Literal["humanReviewed", "unreviewed", "generated"]

SUPPORTED_FORMAT_VERSIONS = frozenset({1})
RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Syrc", "Thaa", "Nkoo", "Adlm", "Mand", "Samr"})


def derive_direction(script: str) -> TextDirection:
    return "rtl" if script in RTL_SCRIPTS else "ltr"


def _is_canonical_bcp47(code: str) -> bool:
    subtags = code.split("-")
    if subtags[0] != subtags[0].lower():
        return False
    script_seen = False
    extension_seen = False
    private_use = False
    for subtag in subtags[1:]:
        if private_use or extension_seen:
            canonical = subtag.lower()
        elif subtag.lower() == "x":
            canonical = subtag.lower()
            private_use = True
        elif len(subtag) == 1 and subtag.isalnum():
            canonical = subtag.lower()
            extension_seen = True
        elif not script_seen and len(subtag) == 4 and subtag.isalpha():
            canonical = subtag.title()
            script_seen = True
        elif (len(subtag) == 2 and subtag.isalpha()) or (
            len(subtag) == 3 and subtag.isdigit()
        ):
            canonical = subtag.upper()
        else:
            canonical = subtag.lower()
        if subtag != canonical:
            return False
    return True


class LanguageSpeech(ApiModel):
    synthesis_locale: LanguageTag
    synthesis: Literal["browserVoice", "none"]
    recognition: bool

    @field_validator("synthesis_locale")
    @classmethod
    def validate_synthesis_locale(cls, value: str) -> str:
        if not _is_canonical_bcp47(value):
            raise ValueError("synthesis_locale must use canonical BCP 47 casing")
        return value


class PackLanguage(ApiModel):
    code: LanguageTag
    locale: LanguageTag
    script: ScriptCode
    direction: TextDirection
    word_separator: WordSeparator
    speech: LanguageSpeech

    @field_validator("code", "locale")
    @classmethod
    def validate_canonical_code(cls, value: str) -> str:
        if not _is_canonical_bcp47(value):
            raise ValueError("language codes must use canonical BCP 47 casing")
        return value

    @model_validator(mode="after")
    def validate_direction(self) -> PackLanguage:
        if self.direction != derive_direction(self.script):
            raise ValueError("direction must match the script direction")
        return self


class Variety(ApiModel):
    variety_id: ContractId
    description: NonEmptyText


class Register(ApiModel):
    register_id: ContractId
    description: NonEmptyText


class Provenance(ApiModel):
    source: NonEmptyText
    review_status: ReviewStatus
    reviewers: list[NonEmptyText] = Field(default_factory=list)
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def validate_review_status(self) -> Provenance:
        if self.review_status == "humanReviewed" and not self.reviewers:
            raise ValueError("humanReviewed provenance requires at least one reviewer")
        if self.review_status != "humanReviewed" and self.reviewers:
            raise ValueError("unreviewed and generated provenance cannot list reviewers")
        return self


class PackLabel(ApiModel):
    semantic: ContractId
    text: NonEmptyText
    provenance: Provenance


class ExampleFact(ApiModel):
    fact_id: NonEmptyText
    label: ContractId


class SentenceChunk(ApiModel):
    text: NonEmptyText
    join: ChunkJoin

    @field_validator("text", mode="before")
    @classmethod
    def reject_chunk_whitespace(cls, value: object) -> object:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("chunk text cannot have leading or trailing whitespace")
        return value

    @field_validator("text")
    @classmethod
    def require_nfc(cls, value: str) -> str:
        if normalize("NFC", value) != value:
            raise ValueError("chunk text must be NFC")
        return value


class ConstructionExample(ApiModel):
    example_id: ContractId
    meaning: NonEmptyText
    facts: list[ExampleFact] = Field(default_factory=list)
    bindings: dict[ContractId, NonEmptyText] = Field(default_factory=dict)
    sentence: NonEmptyText
    translation: NonEmptyText
    chunks: list[SentenceChunk] = Field(min_length=1)
    accepted_alternatives: list[NonEmptyText] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_bindings(self) -> ConstructionExample:
        fact_ids_list = [fact.fact_id for fact in self.facts]
        if len(fact_ids_list) != len(set(fact_ids_list)):
            raise ValueError("example fact IDs must be unique")
        fact_ids = set(fact_ids_list)
        if unknown := set(self.bindings.values()) - fact_ids:
            raise ValueError(f"bindings reference undeclared facts: {sorted(unknown)}")
        if normalize("NFC", self.sentence) != self.sentence:
            raise ValueError("sentence must be NFC")
        if any(normalize("NFC", value) != value for value in self.accepted_alternatives):
            raise ValueError("accepted alternatives must be NFC")
        return self


class IncorrectExample(ApiModel):
    example_id: ContractId
    sentence: NonEmptyText
    correction: NonEmptyText
    note: NonEmptyText
    provenance: Provenance


class Construction(ApiModel):
    construction_id: ContractId
    version: ContentVersion
    summary: NonEmptyText
    guidance: Annotated[str, Field(max_length=600)]
    required_labels: list[ContractId] = Field(default_factory=list)
    provenance: Provenance
    examples: list[ConstructionExample] = Field(default_factory=list)
    incorrect: list[IncorrectExample] = Field(default_factory=list)

    @field_validator("guidance")
    @classmethod
    def require_nfc_guidance(cls, value: str) -> str:
        if normalize("NFC", value) != value:
            raise ValueError("guidance must be NFC")
        return value


class LanguagePack(ApiModel):
    format_version: int
    pack_id: ContractId
    pack_version: Annotated[int, Field(ge=1)]
    instruction_language: LanguageTag
    language: PackLanguage
    variety: Variety
    language_register: Register = Field(alias="register")
    provenance: Provenance
    labels: list[PackLabel] = Field(min_length=1)
    constructions: list[Construction] = Field(min_length=1)
    _pack_dir: Path | None = PrivateAttr(default=None)

    @field_validator("instruction_language")
    @classmethod
    def validate_instruction_language(cls, value: str) -> str:
        if not _is_canonical_bcp47(value):
            raise ValueError("instruction_language must use canonical BCP 47 casing")
        return value

    @model_validator(mode="after")
    def validate_pack_references(self) -> LanguagePack:
        label_ids = [label.semantic for label in self.labels]
        construction_ids = [item.construction_id for item in self.constructions]
        example_ids = [
            item.example_id
            for construction in self.constructions
            for item in (*construction.examples, *construction.incorrect)
        ]
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("label semantic ids must be unique")
        if len(construction_ids) != len(set(construction_ids)):
            raise ValueError("construction ids must be unique")
        if len(example_ids) != len(set(example_ids)):
            raise ValueError("example ids must be unique")

        known_labels = set(label_ids)
        for construction in self.constructions:
            if unknown := set(construction.required_labels) - known_labels:
                raise ValueError(
                    f"{construction.construction_id} has unknown required labels: "
                    f"{sorted(unknown)}"
                )
            for example in construction.examples:
                if unknown := {fact.label for fact in example.facts} - known_labels:
                    raise ValueError(
                        f"{example.example_id} has unknown fact labels: {sorted(unknown)}"
                    )
                if join_pack_chunks(example.chunks, self.language.word_separator) != (
                    example.sentence
                ):
                    raise ValueError(f"{example.example_id} chunks do not reconstruct sentence")
        if self.format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise ValueError(f"unsupported format_version {self.format_version}")
        return self


class GuidanceBundle(ApiModel):
    language: PackLanguage
    variety: Variety
    language_register: Register = Field(alias="register")
    labels: list[PackLabel]
    constructions: list[Construction]


def join_pack_chunks(chunks: list[SentenceChunk], word_separator: WordSeparator) -> str:
    if not chunks:
        return ""
    separator = " " if word_separator == "space" else ""
    return chunks[0].text + "".join(
        (separator if chunk.join == "space" else "") + chunk.text for chunk in chunks[1:]
    )


class EvaluationCase(ApiModel):
    case_id: ContractId
    construction_id: ContractId
    construction_version: ContentVersion
    facts: list[ExampleFact] = Field(default_factory=list)
    bindings: dict[ContractId, NonEmptyText] = Field(default_factory=dict)
    expected: list[NonEmptyText] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_bindings(self) -> EvaluationCase:
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("evaluation fact IDs must be unique")
        declared = set(fact_ids)
        if unknown := set(self.bindings.values()) - declared:
            raise ValueError(f"bindings reference undeclared facts: {sorted(unknown)}")
        if any(normalize("NFC", value) != value for value in self.expected):
            raise ValueError("expected sentences must be NFC")
        return self


class MissionKey(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion


class ConstructionRequirement(ApiModel):
    construction_id: ContractId
    min_version: ContentVersion


class MissionSlotTemplate(ApiModel):
    purpose: NonEmptyText
    construction_id: ContractId
    target_ids: list[ContractId] = Field(min_length=1)
    repeat: Annotated[int, Field(ge=1)] = 1
    required_labels: list[ContractId] = Field(default_factory=list)


class MissionTemplate(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    sequence_repeat: Annotated[int, Field(ge=1)] = 1
    required_constructions: list[ConstructionRequirement]
    required_labels: list[ContractId] = Field(default_factory=list)
    slots: list[MissionSlotTemplate] = Field(min_length=1)

    @property
    def key(self) -> tuple[str, str, int]:
        level = getattr(self.practice_level, "value", self.practice_level)
        return self.mission_id, str(level), self.content_version


class MissionCatalog(ApiModel):
    missions: list[MissionTemplate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_missions(self) -> MissionCatalog:
        keys = [item.key for item in self.missions]
        if len(keys) != len(set(keys)):
            raise ValueError("mission keys must be unique")
        return self
