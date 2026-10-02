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
from app.services.scene_analysis import SceneAnalysisError


class SceneTranslationError(SceneAnalysisError):
    """The confirmed scene could not be translated reliably."""


_LEADING_ARTICLE = re.compile(
    r"^((?:el|la|los|las|le|les)\s+|l['’])", re.IGNORECASE
)


def normalize_object_articles(
    result: SceneTranslationResult,
) -> SceneTranslationResult:
    """Move a definite article inlined in an object ``translation`` into ``article``.

    Models sometimes return "el camino" alongside ``article="el"``; rendering
    prepends the article again, producing "el el camino". Stripping here keeps
    the stored term article-free so downstream rendering stays idempotent.
    """
    objects = []
    for term in result.objects:
        match = _LEADING_ARTICLE.match(term.translation)
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
    if any(not row.article for row in result.objects):
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
