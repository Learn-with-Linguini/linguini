"""Optional saved display metadata; existing tasks need no context or migration."""

from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel, NonEmptyText


class LanguageDisplayContext(ApiModel):
    pack_id: NonEmptyText
    pack_version: int
    fingerprint: NonEmptyText
    language_code: NonEmptyText
    locale: NonEmptyText
    variety: NonEmptyText
    register_id: NonEmptyText = Field(alias="register")
    script: NonEmptyText
    direction: Literal["ltr", "rtl"]
    articles: Literal["required", "optional", "none"]
    grammatical_gender: Literal["required", "optional", "none"]
    romanization_required: bool
    romanization_convention: str | None = None
    speech_locale: NonEmptyText
    speech_synthesis: Literal["browserVoice", "none"]
    speech_recognition: bool

