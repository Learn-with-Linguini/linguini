"""Cached central language registry."""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

from app.schemas.languages import Language

REGISTRY_PATH = Path(__file__).with_name("registry.toml")


@cache
def _load_languages() -> tuple[Language, ...]:
    data = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = tuple(Language.model_validate(entry) for entry in data["languages"])
    codes = [entry.code.casefold() for entry in entries]
    if len(codes) != len(set(codes)):
        raise ValueError("language registry codes must be unique")
    return entries


def languages() -> list[Language]:
    """Return all registered languages in registry order."""
    return list(_load_languages())


def learnable_languages() -> list[Language]:
    """Return languages currently offered as learning targets."""
    return [language for language in _load_languages() if language.learnable]


def get_language(code: str) -> Language | None:
    """Look up a registered language without regard to code casing."""
    normalized = code.casefold()
    return next(
        (language for language in _load_languages() if language.code.casefold() == normalized),
        None,
    )


def is_registered(code: str) -> bool:
    return get_language(code) is not None


__all__ = ["get_language", "is_registered", "languages", "learnable_languages"]
