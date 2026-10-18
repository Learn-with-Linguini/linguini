"""Provider-neutral, deterministic validation for scene translations.

No SDK imports: the same rules run regardless of which adapter produced the
response. ``SceneTranslationError`` stays a ``SceneAnalysisError`` so the
workflow and learning-error handling are unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.features.translation.schemas import (
    SceneTranslationRequest,
    SceneTranslationResult,
)
from app.languages import get_language
from app.services.scene_analysis import SceneAnalysisError

SCENE_TRANSLATION_VALIDATOR_VERSION = "scene-translation-validator.v2"
"""Bump when validation rules change, so cached results stop matching."""


class SceneTranslationError(SceneAnalysisError):
    """The confirmed scene could not be translated reliably."""


_LEADING_ARTICLE = re.compile(
    r"^((?:el|la|los|las|le|les|der|die|das)\s+|l['’])", re.IGNORECASE
)
_GERMAN_ARTICLES = {"der", "die", "das"}


def _requires_articles(language: str | None) -> bool:
    entry = get_language(language or "")
    return bool(entry and entry.grammar and entry.grammar.get("articles") is True)


def normalize_object_articles(
    result: SceneTranslationResult,
    language: str | None = None,
) -> SceneTranslationResult:
    """Move a definite article inlined in an object ``translation`` into ``article``.

    Models sometimes return "el camino" alongside ``article="el"``; rendering
    prepends the article again, producing "el el camino". Stripping here keeps
    the stored term article-free so downstream rendering stays idempotent.
    """
    if not _requires_articles(language):
        return result.model_copy(update={
            "objects": [
                term.model_copy(update={"article": None}) for term in result.objects
            ]
        })

    objects = []
    entry = get_language(language or "")
    grammar = entry.grammar or {} if entry else {}
    gender_values = grammar.get("grammatical_gender")
    supports_neuter = isinstance(gender_values, list) and "neuter" in gender_values
    for term in result.objects:
        match = _LEADING_ARTICLE.match(term.translation)
        if match and match.group(1).strip().casefold() in _GERMAN_ARTICLES and not supports_neuter:
            match = None
        remainder = term.translation[match.end():] if match else ""
        if not match or not remainder:
            objects.append(term)
            continue
        stripped = match.group(1).rstrip()
        update: dict[str, Any] = {"translation": remainder}
        if not term.article:
            update["article"] = stripped.lower()
        objects.append(term.model_copy(update=update))
    return result.model_copy(update={"objects": objects})


def normalize_grammar_fields(
    result: SceneTranslationResult,
    language_code: str | None = None,
) -> SceneTranslationResult:
    """Keep object grammar metadata within the registered language's features."""
    entry = get_language(language_code or "")
    grammar = entry.grammar or {} if entry else {}
    gender_values = grammar.get("grammatical_gender")
    allowed_genders = gender_values if isinstance(gender_values, list) else []
    articles = bool(grammar.get("articles"))
    objects = [
        term.model_copy(update={
            "article": term.article if articles else None,
            "gender": term.gender if term.gender in allowed_genders else None,
        })
        for term in result.objects
    ]
    return result.model_copy(update={"objects": objects})


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
) -> None:
    for field in ("objects", "attributes", "relationships"):
        supplied = _supplied_terms(payload, field)
        returned = {(row.key, row.source) for row in getattr(result, field)}
        if supplied != returned:
            raise SceneTranslationError(
                f"Translation changed or omitted supplied {field}."
            )
    language = (
        payload.target_language if isinstance(payload, SceneTranslationRequest)
        else payload.get("targetLanguage", payload.get("target_language", ""))
    ).lower()
    if _requires_articles(language) and any(not row.article for row in result.objects):
        raise SceneTranslationError(
            "Every translated object requires a definite article."
        )
    if any(
        row.article or row.gender
        for row in [*result.attributes, *result.relationships]
    ):
        raise SceneTranslationError(
            "Only object translations may include articles or gender."
        )
