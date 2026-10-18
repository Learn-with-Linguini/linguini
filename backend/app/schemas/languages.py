"""Language registry response contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import computed_field, field_validator
from pydantic.types import StringConstraints

from app.schemas.base import ApiModel, LanguageCode, NonEmptyText

type LinguisticMetadataValue = str | bool | int | list[str]
type ScriptCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][a-z]{3}$")]
type TextDirection = Literal["ltr", "rtl"]

RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Syrc", "Thaa", "Nkoo", "Adlm", "Mand", "Samr"})


def derive_direction(script: str) -> TextDirection:
    """Derive text direction from the ISO 15924 script code."""
    return "rtl" if script in RTL_SCRIPTS else "ltr"


def _is_canonical_bcp47(code: str) -> bool:
    subtags = code.split("-")
    if subtags[0] != subtags[0].lower():
        return False
    for subtag in subtags[1:]:
        if len(subtag) == 4 and subtag.isalpha():
            canonical = subtag.title()
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
    synthesis_locale: LanguageCode
    synthesis: Literal["browserVoice"] = "browserVoice"
    recognition: Literal[False] = False


class LanguageFeatures(ApiModel):
    mission_levels: list[str]


class Language(ApiModel):
    code: LanguageCode
    english_name: NonEmptyText
    native_name: NonEmptyText
    script: ScriptCode
    flag: str | None = None
    word_separator: Literal["space", "none"] = "space"
    learnable: bool
    instruction: bool
    speech: LanguageSpeech
    grammar: dict[str, LinguisticMetadataValue] | None = None

    @field_validator("code")
    @classmethod
    def validate_canonical_code(cls, value: str) -> str:
        if not _is_canonical_bcp47(value):
            raise ValueError("language code must use canonical BCP 47 casing")
        return value

    @computed_field
    @property
    def direction(self) -> TextDirection:
        return derive_direction(self.script)

    @computed_field
    @property
    def features(self) -> LanguageFeatures:
        return LanguageFeatures(mission_levels=_mission_levels_for_language(self.code))


def _mission_levels_for_language(code: str) -> list[str]:
    from app.missions import get_mission
    from app.missions.m01_multilingual import m01_generation_enabled_for
    from app.services.mission_eligibility import (
        IMPLEMENTED_MISSIONS,
        LEVEL_LANGUAGES,
        MISSION_LANGUAGES,
    )

    levels = []
    for level, variants in IMPLEMENTED_MISSIONS.items():
        accepted_languages = LEVEL_LANGUAGES.get(level, MISSION_LANGUAGES)
        legacy_level = (
            code in accepted_languages
            and any(get_mission(*variant) for variant in variants)
        )
        multilingual_level = (
            m01_generation_enabled_for(code, level)
            and get_mission("M01", level, 1) is not None
        )
        if legacy_level or multilingual_level:
            levels.append(level)
    return levels


class LanguageListResponse(ApiModel):
    items: list[Language]
