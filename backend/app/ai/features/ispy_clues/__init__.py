"""I-Spy clue generation: prompt, schemas, validation, and a traced service.

Exports resolve lazily via ``__getattr__`` — ``app.services.scene_analysis``
and ``app.schemas.sessions`` sit upstream of this package on the import
chain, so eager re-exports would close a circular import.
"""

from typing import Any

_IMPORTS = {
    "ISPY_CLUE_PROMPT_VERSION": ".prompt",
    "ISPY_CLUE_SCHEMA_VERSION": ".prompt",
    "ISPY_CLUE_SYSTEM_PROMPT": ".prompt",
    "GeneratedISpyClue": ".schemas",
    "ISpyClueResult": ".schemas",
    "scene_clue_response_model": ".schemas",
    "ISpyClueGenerationError": ".validation",
    "validate_ispy_clues": ".validation",
    "ISpyClueService": ".service",
}


def __getattr__(name: str) -> Any:
    module = _IMPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value
