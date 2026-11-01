"""Provider-neutral, deterministic validation for scene translations.

No SDK imports: the same rules run regardless of which adapter produced the
response. ``SceneTranslationError`` stays a ``SceneAnalysisError`` so the
workflow and learning-error handling are unchanged.
"""

from __future__ import annotations

from typing import Any

from app.ai.features.translation.schemas import (
    SceneTranslationRequest,
    SceneTranslationResult,
)
from app.services.scene_analysis import SceneAnalysisError


class SceneTranslationError(SceneAnalysisError):
    """The confirmed scene could not be translated reliably."""


def _supplied_terms(payload: dict[str, Any] | SceneTranslationRequest, field: str) -> set:
    rows = getattr(payload, field) if isinstance(
        payload, SceneTranslationRequest
    ) else payload[field]
    return {(row.key if hasattr(row, "key") else row["key"],
             row.source if hasattr(row, "source") else row["source"])
            for row in rows}


def validate_translation_terms(
    payload: dict[str, Any] | SceneTranslationRequest,
    result: SceneTranslationResult,
    language_context,
) -> None:
    """Every supplied term comes back once, unchanged, and as the language pack requires."""
    validate_supplied_terms(payload, result)
    validate_pack_translation(result, language_context)


def validate_supplied_terms(
    payload: dict[str, Any] | SceneTranslationRequest, result: SceneTranslationResult,
) -> None:
    """The language-independent contract: every supplied key and source comes back once,
    and only objects carry an article or gender."""
    for field in ("objects", "attributes", "relationships"):
        supplied = _supplied_terms(payload, field)
        returned = {(row.key, row.source) for row in getattr(result, field)}
        if supplied != returned:
            raise SceneTranslationError(
                f"Translation changed or omitted supplied {field}."
            )
    if any(
        row.article or row.gender
        for row in [*result.attributes, *result.relationships]
    ):
        raise SceneTranslationError(
            "Only object translations may include articles or gender."
        )


def validate_pack_translation(result, context):
    from unicodedata import name, normalize

    settings = context.display
    for term in result.objects:
        for field, policy in (("article", settings.articles),
                              ("gender", settings.grammatical_gender)):
            value = getattr(term, field)
            if (policy == "required" and not value) or (policy == "none" and value):
                raise SceneTranslationError(f"Pack {field} policy {policy!r} failed for {term.key}")
    for term in [*result.objects, *result.attributes, *result.relationships]:
        if not term.native_display:
            raise SceneTranslationError(f"Pack vocabulary requires nativeDisplay for {term.key}")
        if normalize("NFC", term.native_display) != term.native_display:
            raise SceneTranslationError("Vocabulary nativeDisplay must preserve NFC Unicode")
        if settings.romanization_required and not term.romanization:
            raise SceneTranslationError(f"Pack vocabulary requires romanization for {term.key}")
        if term.romanization and any(c.isalpha() and "LATIN" not in name(c, "")
                                     for c in term.romanization):
            raise SceneTranslationError("Vocabulary romanization must use Latin letters")
