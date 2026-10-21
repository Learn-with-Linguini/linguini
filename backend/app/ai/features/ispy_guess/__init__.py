"""I-Spy description evaluation: prompt, schemas, validation, and a traced service.

Exports resolve lazily via ``__getattr__`` — ``app.services.scene_analysis``
sits upstream of this package on the import chain, so eager re-exports would
close a circular import.
"""

from typing import Any

_IMPORTS = {
    "ISPY_GUESS_PROMPT_VERSION": ".prompt",
    "ISPY_GUESS_SCHEMA_VERSION": ".prompt",
    "ISPY_GUESS_SYSTEM_PROMPT": ".prompt",
    "ISpyGuessResult": ".schemas",
    "scene_guess_response_model": ".schemas",
    "MAX_LEARNER_TEXT_LENGTH": ".validation",
    "ISpyGuessError": ".validation",
    "build_guess_payload": ".validation",
    "validate_ispy_guess": ".validation",
    "ISpyGuessService": ".service",
}


def __getattr__(name: str) -> Any:
    module = _IMPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value
