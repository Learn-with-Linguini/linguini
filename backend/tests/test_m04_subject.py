"""Owned-object sentence assembly must retain the complete noun phrase."""

import pytest

from app.language_packs.lessons.m04 import _split_subject


@pytest.mark.parametrize(("text", "noun", "expected"), [
    ("El banco de parque es mío.", "banco de parque", ("El banco de parque", "es mío")),
    ("El banco de parque es tuyo.", "banco de parque", ("El banco de parque", "es tuyo")),
    ("La taza es mía.", "taza", ("La taza", "es mía")),
    ("L’ordinateur portable est à moi.", "ordinateur portable",
     ("L’ordinateur portable", "est à moi")),
    ("커피 컵은 제 거예요.", "커피 컵", ("커피 컵은", "제 거예요")),
    ("컵은 제 거예요.", "컵", ("컵은", "제 거예요")),
])
def test_owned_subject_contains_the_full_noun_phrase(text, noun, expected):
    assert _split_subject(text, {"noun": noun}) == expected


@pytest.mark.parametrize(("text", "noun"), [
    ("El banco es mío.", "banco de parque"),
    ("El banco del parque es mío.", "banco de parque"),
    ("El banco de parque.", "banco de parque"),
])
def test_missing_or_incomplete_noun_phrase_is_rejected(text, noun):
    with pytest.raises(ValueError, match="cannot find the owned noun"):
        _split_subject(text, {"noun": noun})
