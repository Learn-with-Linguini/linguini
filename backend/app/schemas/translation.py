"""Re-export shim: the translation contracts now live in the feature package.

``app.ai.features.translation.schemas`` owns both the request and result
models; this module stays so ``app/schemas/sessions.py`` (``translation_preview``)
and existing imports keep working unchanged.
"""

from app.ai.features.translation.schemas import (
    SceneTranslationResult,
    TranslatedTerm,
)

__all__ = ["SceneTranslationResult", "TranslatedTerm"]
