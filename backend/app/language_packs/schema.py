"""Strict language-pack data contracts."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import Field, PrivateAttr, StringConstraints, field_validator, model_validator

from app.ai.features.scene_analysis.schemas import SceneAttributeType
from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import ProficiencyLevel, SceneRelationType
from app.schemas.tasks import ContentVersion, ContractId, MissionId

type ScriptCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][a-z]{3}$")]
# A check's regular expression, kept exactly as written: edge spaces are word boundaries.
type CheckPattern = Annotated[str, StringConstraints(min_length=1, strip_whitespace=False)]
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
type LabelUsage = Literal["prompt", "sentence"]
type PartOfSpeech = Literal[
    "noun", "adjective", "determiner", "phrase", "preposition", "verb", "other",
]

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
    romanization_required: bool = False
    romanization_convention: NonEmptyText | None = None
    articles: Literal["required", "optional", "none"] = "optional"
    grammatical_gender: Literal["required", "optional", "none"] = "optional"
    phrase_boundaries: list[NonEmptyText] = Field(default_factory=list)
    # "suffixing": particles and case endings attach to the word (Korean 컵이에요), so a
    # bound noun may appear inside a longer word. ``stem_endings`` are final letters a
    # stem may lose before a suffix in languages that drop them.
    inflection: Literal["none", "suffixing"] = "none"
    stem_endings: list[NonEmptyText] = Field(default_factory=list)

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
    meaning: NonEmptyText
    usage: LabelUsage
    provenance: Provenance
    romanization: NonEmptyText | None = None


class PackFiles(ApiModel):
    labels: NonEmptyText
    # Number words for counting missions (M03); packs without it do not offer them.
    numbers: NonEmptyText | None = None
    # Possessive words and the role-play cast for ownership missions (M04).
    possessives: NonEmptyText | None = None
    constructions: list[NonEmptyText] = Field(min_length=1)
    examples: list[NonEmptyText] = Field(min_length=1)
    evaluations: list[NonEmptyText] = Field(min_length=1)


class LabelsFile(ApiModel):
    labels: list[PackLabel] = Field(min_length=1)


class NumberForm(ApiModel):
    """How a number is written next to a counted noun, when that differs from ``text``.

    ``agreement`` limits the form to nouns of one gender (Spanish un/una); a form
    without one applies to every noun (Korean 두 개 with its counter).
    """

    text: NonEmptyText
    agreement: Literal["masculine", "feminine", "neuter"] | None = None
    romanization: NonEmptyText | None = None


class PackNumber(ApiModel):
    value: Annotated[int, Field(ge=1, le=20)]
    text: NonEmptyText
    romanization: NonEmptyText | None = None
    with_noun: list[NumberForm] = Field(default_factory=list)

    def form_for(self, agreement: str | None) -> NumberForm:
        """The form used with a noun of this agreement (the number itself by default)."""
        return next(
            (form for form in self.with_noun if form.agreement == agreement),
            next(
                (form for form in self.with_noun if form.agreement is None),
                NumberForm(text=self.text, romanization=self.romanization),
            ),
        )

    @property
    def texts(self) -> list[str]:
        return list(dict.fromkeys([self.text, *(form.text for form in self.with_noun)]))


class NumbersFile(ApiModel):
    provenance: Provenance
    numbers: list[PackNumber] = Field(min_length=1)

    @field_validator("numbers")
    @classmethod
    def require_unique_values(cls, value: list[PackNumber]) -> list[PackNumber]:
        values = [number.value for number in value]
        if len(values) != len(set(values)):
            raise ValueError("number values must be unique")
        for number in value:
            agreements = [form.agreement for form in number.with_noun]
            if len(agreements) != len(set(agreements)):
                raise ValueError(f"number {number.value} repeats a with_noun agreement")
        return value

    def get(self, value: int) -> PackNumber | None:
        return next((number for number in self.numbers if number.value == value), None)

    @property
    def values(self) -> set[int]:
        return {number.value for number in self.numbers}


Agreement = Literal["masculine", "feminine", "neuter"]
# Who a possessive refers to: the speaker, the listener, or a third person by gender.
Possessor = Literal["first", "second", "third-masculine", "third-feminine"]


class PossessiveForm(ApiModel):
    """One written possessive: before a noun (``determiner``: mi, ma, meine, 제) or as
    the predicate (``predicate``: es mía, à moi, gehört mir).

    ``agreement`` limits the form to nouns of one gender; ``before_vowel`` marks a form
    used before a vowel instead (French mon before a feminine noun such as assiette).
    """

    text: NonEmptyText
    use: Literal["determiner", "predicate"]
    agreement: Agreement | None = None
    before_vowel: bool = False
    romanization: NonEmptyText | None = None

    @property
    def key(self) -> str:
        return f"{self.use}-{self.agreement or 'any'}" + ("-vowel" if self.before_vowel else "")


class PackPossessor(ApiModel):
    possessor: Possessor
    meaning: NonEmptyText
    # A language may name third-person owners only by name (Korean 아나의); then empty.
    forms: list[PossessiveForm] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_keys(self) -> PackPossessor:
        keys = [form.key for form in self.forms]
        if len(keys) != len(set(keys)):
            raise ValueError(f"possessor {self.possessor} repeats a use and agreement")
        return self


class CastMember(ApiModel):
    """A role-play owner: the name a lesson uses for someone else's things."""

    owner_id: ContractId
    english_name: NonEmptyText
    name: NonEmptyText
    gender: Literal["masculine", "feminine"]
    romanization: NonEmptyText | None = None


class PossessivesFile(ApiModel):
    provenance: Provenance
    possessors: list[PackPossessor] = Field(min_length=1)
    cast: list[CastMember] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_entries(self) -> PossessivesFile:
        possessors = [item.possessor for item in self.possessors]
        owners = [item.owner_id for item in self.cast]
        if len(possessors) != len(set(possessors)) or len(owners) != len(set(owners)):
            raise ValueError("possessors and cast owners must be unique")
        if {"first", "second"} & set(owners):
            raise ValueError("cast owner ids cannot be first or second")
        return self

    def get(self, possessor: str) -> PackPossessor | None:
        return next((item for item in self.possessors if item.possessor == possessor), None)

    def member(self, owner_id: str) -> CastMember | None:
        return next((item for item in self.cast if item.owner_id == owner_id), None)


class SceneObject(ApiModel):
    fact_id: NonEmptyText
    concept: NonEmptyText

    @model_validator(mode="after")
    def validate_fact_id(self) -> SceneObject:
        if self.fact_id != f"object:{self.concept}":
            raise ValueError("object fact_id must be object:<concept>")
        return self


class SceneAttribute(ApiModel):
    fact_id: NonEmptyText
    object: NonEmptyText
    kind: SceneAttributeType
    value: NonEmptyText


class SceneRelation(ApiModel):
    fact_id: NonEmptyText
    subject: NonEmptyText
    reference: NonEmptyText
    relation: SceneRelationType


class SceneCount(ApiModel):
    fact_id: NonEmptyText
    object: NonEmptyText
    quantity: Annotated[int, Field(ge=1, le=20)]


class SceneOwner(ApiModel):
    """Who an object belongs to: ``first`` (the learner) or a cast owner ID."""

    fact_id: NonEmptyText
    object: NonEmptyText
    owner: ContractId


class ExampleScene(ApiModel):
    objects: list[SceneObject] = Field(default_factory=list)
    absent: list[SceneObject] = Field(default_factory=list)
    attributes: list[SceneAttribute] = Field(default_factory=list)
    relations: list[SceneRelation] = Field(default_factory=list)
    counts: list[SceneCount] = Field(default_factory=list)
    owners: list[SceneOwner] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> ExampleScene:
        facts = [
            *(item.fact_id for item in self.objects),
            *(item.fact_id for item in self.absent),
            *(item.fact_id for item in self.attributes),
            *(item.fact_id for item in self.relations),
            *(item.fact_id for item in self.counts),
            *(item.fact_id for item in self.owners),
        ]
        if len(facts) != len(set(facts)):
            raise ValueError("scene fact IDs must be unique")
        object_ids = {item.fact_id for item in self.objects}
        if unknown := {
            *(item.object for item in self.attributes),
            *(item.subject for item in self.relations),
            *(item.reference for item in self.relations),
            *(item.object for item in self.counts),
            *(item.object for item in self.owners),
        } - object_ids:
            raise ValueError(f"scene references undeclared objects: {sorted(unknown)}")
        if any(item.subject == item.reference for item in self.relations):
            raise ValueError("relation subjects and references must differ")
        return self

    @property
    def fact_ids(self) -> set[str]:
        return {
            *(item.fact_id for item in self.objects),
            *(item.fact_id for item in self.absent),
            *(item.fact_id for item in self.attributes),
            *(item.fact_id for item in self.relations),
            *(item.fact_id for item in self.counts),
            *(item.fact_id for item in self.owners),
        }

    @property
    def absent_fact_ids(self) -> set[str]:
        return {item.fact_id for item in self.absent}

    def validate_bindings(self, bindings: dict[str, str], truth: bool) -> None:
        # A pack number (``number:7``: a practice board, a friend's wrong count) is pack
        # data rather than a scene fact, so only false sentences may name one.
        numbers = {value for value in bindings.values() if re.fullmatch(r"number:\d+", value)}
        # A pack possessor (``possessor:second``: "is it yours?") is pack data too.
        possessors = {
            value for value in bindings.values() if re.fullmatch(r"possessor:[a-z-]+", value)
        }
        if unknown := set(bindings.values()) - self.fact_ids - numbers - possessors:
            raise ValueError(f"bindings reference undeclared facts: {sorted(unknown)}")
        if truth and numbers:
            raise ValueError(f"true examples cannot bind pack numbers: {sorted(numbers)}")
        if truth and (absent := set(bindings.values()) & self.absent_fact_ids):
            raise ValueError(f"true examples cannot bind absent facts: {sorted(absent)}")


class ExampleContrast(ApiModel):
    sentence: NonEmptyText
    note: NonEmptyText


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
    levels: list[ProficiencyLevel] = Field(min_length=1)
    purposes: list[NonEmptyText] = Field(min_length=1)
    meaning: NonEmptyText
    scene: ExampleScene
    bindings: dict[ContractId, NonEmptyText] = Field(default_factory=dict)
    truth: bool = True
    labels: list[ContractId] = Field(default_factory=list)
    sentence: NonEmptyText
    translation: NonEmptyText
    chunks: list[SentenceChunk] = Field(min_length=1)
    accepted_alternatives: list[NonEmptyText] = Field(default_factory=list)
    contrasts: list[ExampleContrast] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_bindings(self) -> ConstructionExample:
        self.scene.validate_bindings(self.bindings, self.truth)
        if normalize("NFC", self.sentence) != self.sentence:
            raise ValueError("sentence must be NFC")
        if any(normalize("NFC", value) != value for value in self.accepted_alternatives):
            raise ValueError("accepted alternatives must be NFC")
        return self


class IncorrectExample(ApiModel):
    example_id: ContractId
    levels: list[ProficiencyLevel] = Field(min_length=1)
    purposes: list[NonEmptyText] = Field(min_length=1)
    sentence: NonEmptyText
    correction: NonEmptyText
    note: NonEmptyText
    provenance: Provenance


class ConstructionExamplesFile(ApiModel):
    construction_id: ContractId
    examples: list[ConstructionExample] = Field(default_factory=list)
    mistakes: list[IncorrectExample] = Field(default_factory=list)


def normalize_check_text(text: str) -> str:
    """Text as pack checks see it: NFC, with typographic apostrophes folded."""
    return normalize("NFC", text).replace("’", "'")


class ConstructionCheck(ApiModel):
    """A high-precision surface rule for one construction's generated sentences.

    Patterns are Python regular expressions, matched case-insensitively by default.
    Checks must not depend on exact word spellings: they cannot prove meaning or
    grammaticality, and a check that rejects a valid sentence fails a lesson.
    """

    check_id: ContractId
    message: NonEmptyText
    must_contain: list[CheckPattern] = Field(default_factory=list)
    must_not_contain: list[CheckPattern] = Field(default_factory=list)
    # Plan spec uses (name, question, prompt, answer, option, followup, fact1-3,
    # connected, wrongAttribute, falseFirst, wrongExistence). Empty means every use.
    uses: list[NonEmptyText] = Field(default_factory=list)
    except_uses: list[NonEmptyText] = Field(default_factory=list)
    truth: bool | None = None
    case_sensitive: bool = False

    @model_validator(mode="after")
    def validate_patterns(self) -> ConstructionCheck:
        if not self.must_contain and not self.must_not_contain:
            raise ValueError(f"check {self.check_id!r} needs must_contain or must_not_contain")
        if set(self.uses) & set(self.except_uses):
            raise ValueError(f"check {self.check_id!r} both includes and excludes a use")
        for pattern in [*self.must_contain, *self.must_not_contain]:
            if not pattern.strip():
                raise ValueError(f"check {self.check_id!r} has a blank pattern")
            if normalize("NFC", pattern) != pattern:
                raise ValueError(f"check {self.check_id!r} pattern must be NFC: {pattern!r}")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"check {self.check_id!r} has an invalid pattern {pattern!r}: {exc}"
                ) from None
        return self

    def applies(self, use: str | None, truth: bool | None) -> bool:
        use = use or "answer"
        if self.uses and use not in self.uses:
            return False
        if use in self.except_uses:
            return False
        return self.truth is None or self.truth == (truth is not False)

    def passes(self, text: str) -> bool:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        text = normalize_check_text(text)
        return all(re.search(p, text, flags) for p in self.must_contain) and not any(
            re.search(p, text, flags) for p in self.must_not_contain
        )


class Construction(ApiModel):
    construction_id: ContractId
    version: ContentVersion
    summary: NonEmptyText
    guidance: Annotated[str, Field(max_length=2000)]
    features: list[ContractId] = Field(default_factory=list)
    constraints: list[NonEmptyText] = Field(default_factory=list)
    required_labels: list[ContractId] = Field(default_factory=list)
    roles: dict[NonEmptyText, PartOfSpeech] = Field(default_factory=dict)
    # Optional templates are supports/legacy diagnostics, never the sentence generator.
    templates: dict[str, str] = Field(default_factory=dict)
    # Declarative surface checks run by the shared pack-checks validator.
    checks: list[ConstructionCheck] = Field(default_factory=list)
    provenance: Provenance
    examples: list[ConstructionExample] = Field(default_factory=list)
    mistakes: list[IncorrectExample] = Field(default_factory=list)

    @property
    def incorrect(self) -> list[IncorrectExample]:
        return self.mistakes

    @field_validator("checks")
    @classmethod
    def require_unique_check_ids(cls, value: list[ConstructionCheck]) -> list[ConstructionCheck]:
        ids = [check.check_id for check in value]
        if len(ids) != len(set(ids)):
            raise ValueError("construction check IDs must be unique")
        return value

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
    # Data-driven forms derived from session translations, never a per-language lexicon.
    lexical: dict[str, dict[str, str]] = Field(default_factory=dict)
    numbers: NumbersFile | None = None
    possessives: PossessivesFile | None = None
    _pack_dir: Path | None = PrivateAttr(default=None)
    _evaluation_files: list[Path] = PrivateAttr(default_factory=list)

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
            for item in (*construction.examples, *construction.mistakes)
        ]
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("label semantic ids must be unique")
        if len(construction_ids) != len(set(construction_ids)):
            raise ValueError("construction ids must be unique")
        if len(example_ids) != len(set(example_ids)):
            raise ValueError("example ids must be unique")

        known_labels = set(label_ids)
        labels_by_id = {label.semantic: label for label in self.labels}
        for construction in self.constructions:
            if unknown := set(construction.required_labels) - known_labels:
                raise ValueError(
                    f"{construction.construction_id} has unknown required labels: "
                    f"{sorted(unknown)}"
                )
            for example in construction.examples:
                if unknown := set(example.labels) - known_labels:
                    raise ValueError(
                        f"{example.example_id} has unknown labels: {sorted(unknown)}"
                    )
                if any(
                    labels_by_id[semantic].usage != "sentence"
                    for semantic in example.labels
                ):
                    raise ValueError(
                        f"{example.example_id} labels must be sentence labels"
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
    mission_id: MissionId | None = None
    practice_level: ProficiencyLevel | None = None
    purpose: NonEmptyText | None = None
    prompt_labels: list[ContractId] = Field(default_factory=list)
    sentence_labels: list[ContractId] = Field(default_factory=list)


def join_pack_chunks(chunks: list[SentenceChunk], word_separator: WordSeparator) -> str:
    if not chunks:
        return ""
    separator = " " if word_separator == "space" else ""
    return chunks[0].text + "".join(
        (separator if chunk.join == "space" else "") + chunk.text for chunk in chunks[1:]
    )


class EvaluationReject(ApiModel):
    sentence: NonEmptyText
    reason: NonEmptyText
    category: Literal[
        "wrongObject",
        "wrongAttribute",
        "wrongRelation",
        "wrongCount",
        "wrongOwner",
        "agreement",
        "wordOrder",
        "verbChoice",
        "punctuation",
        "article",
        "languageLeakage",
        "contraction",
        "meaning",
        "unicode",
    ]


class EvaluationCase(ApiModel):
    case_id: ContractId
    category: Literal[
        "valid",
        "wrongObject",
        "wrongAttribute",
        "wrongRelation",
        "wrongCount",
        "wrongOwner",
        "agreement",
        "wordOrder",
        "verbChoice",
        "punctuation",
        "article",
        "languageLeakage",
        "contraction",
        "meaning",
        "unicode",
    ]
    construction_id: ContractId
    construction_version: ContentVersion
    scene: ExampleScene
    bindings: dict[ContractId, NonEmptyText] = Field(default_factory=dict)
    truth: bool
    labels: list[ContractId] = Field(default_factory=list)
    # Plan spec use (for example "name"); inferred from input/punctuation when omitted.
    use: NonEmptyText | None = None
    input: NonEmptyText
    expected_meaning: NonEmptyText
    acceptable: list[NonEmptyText] = Field(min_length=1)
    reject: list[EvaluationReject] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_bindings(self) -> EvaluationCase:
        self.scene.validate_bindings(self.bindings, self.truth)
        if any(normalize("NFC", value) != value for value in self.acceptable):
            raise ValueError("acceptable sentences must be NFC")
        return self


class EvaluationFile(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    cases: list[EvaluationCase] = Field(min_length=1)


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
    additional_constructions: list[ContractId] = Field(default_factory=list)
    target_ids: list[ContractId] = Field(min_length=1)
    repeat: Annotated[int, Field(ge=1)] = 1
    prompt_labels: list[ContractId] = Field(default_factory=list)
    sentence_labels: list[ContractId] = Field(default_factory=list)

    @property
    def required_labels(self) -> list[str]:
        return list(dict.fromkeys([*self.prompt_labels, *self.sentence_labels]))

    @property
    def construction_ids(self) -> list[str]:
        return list(dict.fromkeys([self.construction_id, *self.additional_constructions]))


class MissionTemplate(ApiModel):
    mission_id: MissionId
    practice_level: ProficiencyLevel
    content_version: ContentVersion
    sequence_repeat: Annotated[int, Field(ge=1)] = 1
    required_constructions: list[ConstructionRequirement]
    # Number words the pack must supply (counting missions).
    required_numbers: list[Annotated[int, Field(ge=1, le=20)]] = Field(default_factory=list)
    # Possessors (first, second) and cast owners the pack must supply (ownership missions).
    required_possessors: list[ContractId] = Field(default_factory=list)
    slots: list[MissionSlotTemplate] = Field(min_length=1)

    @property
    def required_labels(self) -> list[str]:
        return list(dict.fromkeys(
            label
            for slot in self.slots
            for label in (*slot.prompt_labels, *slot.sentence_labels)
        ))

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
