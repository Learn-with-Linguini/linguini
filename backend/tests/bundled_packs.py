"""Bundled language packs parsed once per test run.

Parsing a pack reads and validates every TOML file in it, which dominated the
language-pack suites when each test reloaded the same unchanged pack. Tests that edit
pack files still copy the pack and call ``load_pack`` on the copy.
"""

from functools import cache
from pathlib import Path

from app.config import BUNDLED_LANGUAGE_PACKS
from app.language_packs.loader import load_pack
from app.language_packs.schema import LanguagePack


@cache
def _parsed(path: Path) -> LanguagePack:
    return load_pack(path)


def bundled_pack(path: Path) -> LanguagePack:
    """A private copy of the bundled pack at ``path``; tests may change it freely."""
    resolved = Path(path).resolve()
    assert resolved.is_relative_to(Path(BUNDLED_LANGUAGE_PACKS).resolve()), (
        f"{path} is not a bundled pack; load edited copies with load_pack"
    )
    return _parsed(resolved).model_copy(deep=True)
