"""Provider-neutral scene-translation feature package.

Exports are lazy (``__getattr__``) because ``app.schemas.translation`` — a
leaf of ``app.services.scene_analysis``'s import chain — re-exports the
schemas here; eagerly importing ``service``/``validation`` would close a
cycle back onto ``app.services.scene_analysis``.
"""

from typing import Any

__all__ = [
    "SCENE_TRANSLATION_PROMPT_VERSION",
    "SCENE_TRANSLATION_SCHEMA_VERSION",
    "SCENE_TRANSLATION_SYSTEM_PROMPT",
    "SceneTranslationError",
    "SceneTranslationRequest",
    "SceneTranslationResult",
    "SceneTranslationService",
    "TranslatedTerm",
    "TranslationTerm",
    "build_scene_translation_schema",
    "normalize_object_articles",
    "validate_translation_terms",
]

_IMPORTS = {
    "SCENE_TRANSLATION_PROMPT_VERSION": "app.ai.features.translation.prompt",
    "SCENE_TRANSLATION_SCHEMA_VERSION": "app.ai.features.translation.prompt",
    "SCENE_TRANSLATION_SYSTEM_PROMPT": "app.ai.features.translation.prompt",
    "SceneTranslationRequest": "app.ai.features.translation.schemas",
    "SceneTranslationResult": "app.ai.features.translation.schemas",
    "TranslatedTerm": "app.ai.features.translation.schemas",
    "TranslationTerm": "app.ai.features.translation.schemas",
    "SceneTranslationService": "app.ai.features.translation.service",
    "build_scene_translation_schema": "app.ai.features.translation.service",
    "SceneTranslationError": "app.ai.features.translation.validation",
    "normalize_object_articles": "app.ai.features.translation.validation",
    "validate_translation_terms": "app.ai.features.translation.validation",
}


def __getattr__(name: str) -> Any:
    module_path = _IMPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value
    return value
