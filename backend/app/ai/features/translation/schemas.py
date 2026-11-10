"""Structured request and result contracts for scene translation.

The request bounds comfortably exceed real API limits (objects ≤50 + added
≤20, relations ≤100) so valid learner sessions are never rejected while
absurd payloads still fail fast. ``ApiModel`` serializes snake_case fields as
camelCase, matching the workflow payload keys.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas.base import ApiModel, NonEmptyText

_AGREEMENT_GENDERS = frozenset({"masculine", "feminine", "neuter"})


class TranslationTerm(ApiModel):
    key: NonEmptyText = Field(max_length=200)
    source: NonEmptyText = Field(max_length=500)


class SceneTranslationRequest(ApiModel):
    target_language: NonEmptyText = Field(max_length=16)
    scene_title: NonEmptyText = Field(max_length=200)
    scene_summary: str = Field(default="", max_length=1000)
    objects: Annotated[list[TranslationTerm], Field(max_length=70)]
    attributes: Annotated[list[TranslationTerm], Field(max_length=200)] = []
    relationships: Annotated[list[TranslationTerm], Field(max_length=100)] = []


class TranslatedTerm(ApiModel):
    key: NonEmptyText
    source: NonEmptyText
    translation: NonEmptyText = Field(
        max_length=300,
        description=("Required target-language translation for this object, attribute or "
                     "relationship. Never empty or null, including for non-objects."),
    )
    article: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    gender: Literal["masculine", "feminine", "neuter"] | None = None
    agreement_forms: dict[
        Literal["masculine", "feminine", "neuter"], NonEmptyText
    ] = Field(
        default_factory=dict,
        max_length=3,
        description=("Attributes only: standard singular adjective forms by grammatical "
                     "gender. Return every available gender form; otherwise an empty object."),
    )
    native_display: NonEmptyText | None = Field(default=None, exclude_if=lambda v: v is None)
    romanization: NonEmptyText | None = Field(default=None, exclude_if=lambda v: v is None)
    plural: Annotated[str, Field(min_length=1, max_length=300)] | None = Field(
        default=None,
        description=("Objects only: the bare plural noun without an article (Spanish "
                     "\"tazas\", French \"tasses\", German \"Tassen\"); for Korean, "
                     "repeat the bare noun. Null for attributes and relationships."),
    )
    phonetic_text: Annotated[str, Field(min_length=1, max_length=300)] | None = Field(
        default=None,
        description=("Approximate English-sound respelling of the translated word "
                     "(not IPA, no slashes); the stressed syllable in caps, "
                     "e.g. \"MEH-sah\". Supply for every object, attribute and relationship."),
    )

    @field_validator("article", "gender", mode="before")
    @classmethod
    def normalize_string_null(cls, value):
        """Accept a provider spelling JSON null as the literal string ``"null"``."""
        if isinstance(value, str) and value.strip().casefold() == "null":
            return None
        return value

    @field_validator("agreement_forms", mode="before")
    @classmethod
    def drop_unsupported_agreement_keys(cls, value):
        """Keep only gender-keyed forms. Agreement forms are optional enrichment, so a
        provider keying them by number (``singular``/``plural``) loses those forms
        instead of failing the whole translation."""
        if not isinstance(value, dict):
            return value
        forms = {}
        for key, form in value.items():
            gender = key.strip().casefold() if isinstance(key, str) else key
            if gender in _AGREEMENT_GENDERS and gender not in forms:
                forms[gender] = form
        return forms


class SceneTranslationResult(ApiModel):
    objects: Annotated[list[TranslatedTerm], Field(max_length=70)]
    attributes: Annotated[list[TranslatedTerm], Field(max_length=200)]
    relationships: Annotated[list[TranslatedTerm], Field(max_length=100)]


class TranslationReviewIssue(ApiModel):
    group: Literal["objects", "attributes", "relationships"]
    key: NonEmptyText
    issue_type: Literal["meaningMismatch", "formPreference"] = "meaningMismatch"
    # What the current translation actually means, in English.
    current_meaning: NonEmptyText
    # The everyday native word for the source meaning.
    suggestion: NonEmptyText
    problem: NonEmptyText


class TranslationReview(ApiModel):
    """Translations a reviewer is confident do not express their English source."""

    issues: Annotated[list[TranslationReviewIssue], Field(max_length=370)]
