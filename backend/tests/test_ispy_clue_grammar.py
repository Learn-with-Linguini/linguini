"""The I-Spy clue grammar comes from each pack's clues.toml and builds the same clues."""

import json
from pathlib import Path

import pytest
from ispy_clue_cases import GOLDEN, NOUNS, _context, snapshot
from pydantic import ValidationError

from app.language_packs.context import resolve_language_context
from app.language_packs.schema import CluesFile
from app.schemas.media import SceneObject
from app.schemas.vocabulary import VocabularyItem
from app.services import ispy_clue_frames
from app.services.ispy_clue_frames import _grammar_of, clue_grammar

CLUE_LANGUAGES = ("es", "fr", "de", "ko")


def _diff(expected, actual, path=""):
    """The first paths where ``actual`` differs from ``expected``."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return [found for key in sorted(set(expected) | set(actual))
                for found in _diff(expected.get(key), actual.get(key), f"{path}/{key}")][:10]
    return [] if expected == actual else [f"{path}: {expected!r} != {actual!r}"]


def test_pack_clues_build_exactly_what_the_hand_written_tables_built():
    golden = json.loads((Path(__file__).parent / GOLDEN).read_text("utf-8"))
    current = json.loads(json.dumps(snapshot(), ensure_ascii=False))
    assert set(current) == set(CLUE_LANGUAGES)
    assert not _diff(golden, current)


@pytest.mark.parametrize("language", CLUE_LANGUAGES)
def test_every_clue_language_pack_carries_its_grammar(language):
    grammar = clue_grammar(language)
    assert grammar is not None
    assert grammar.articleless is (language == "ko")
    assert grammar.reference_first is (language == "ko")
    assert len(grammar.clues.positions) == 5
    assert any(colour.bank for colour in grammar.clues.colours)


def test_clue_review_is_optional_but_missing_clues_get_no_frames():
    context = resolve_language_context("es")
    pack = json.loads(context.pack_json)
    assert _grammar_of(context.pack_json, True) is not None
    # Human review is optional unless strict release policy is selected.
    assert pack["clues"]["provenance"]["review_status"] == "unreviewed"
    assert _grammar_of(context.pack_json, False) is not None
    assert _grammar_of(context.pack_json, False, require_release=True) is None
    without = json.dumps({**pack, "clues": None}, ensure_ascii=False)
    assert _grammar_of(without, True) is None
    assert clue_grammar(None) is None and clue_grammar("xx") is None


def test_no_grammar_means_no_frames(monkeypatch):
    monkeypatch.setattr(ispy_clue_frames, "clue_grammar", lambda _language: None)
    ids, context = _context("es", "no-grammar", [("cup", "color", "rojo")], [])
    target = SceneObject(id=ids["cup"], session_id=ids["cup"], label="cup")
    word = VocabularyItem(language_code="es", lemma=NOUNS["es"]["cup"][0],
                          display_text=NOUNS["es"]["cup"][0], part_of_speech="noun")
    keys = [str(key) for key in ids.values()]
    assert ispy_clue_frames.build_clue_support(context, target, word, keys) == ([], [])
    assert ispy_clue_frames.agree_colour("es", "rojo", "feminine") is None
    assert ispy_clue_frames._place("es", "sobre", {"translation": "mesa", "article": "la"}) is None


def _clues(**changes):
    data = {
        "provenance": {"source": "test", "review_status": "unreviewed"},
        "prefixes": [{"frame": "colour", "text": "Es"}, {"frame": "location", "text": "Está"}],
        "examples": {"colour": "Es roja.", "location": "Está sobre la mesa."},
        "positions": [{"text": "sobre", "meaning": "on", "example": "Está sobre la mesa."}],
        "colours": [{"meaning": "red", "forms": ["rojo", "roja"], "bank": True}],
    }
    return {**data, **changes}


@pytest.mark.parametrize(("changes", "message"), [
    ({"prefixes": [{"frame": "colour", "text": "Es"}, {"frame": "location", "text": "Está",
                                                        "agreement": "feminine"}]},
     "location entry without agreement"),
    ({"place": "{position}"}, "one {position} and one {reference}"),
    ({"colours": [{"meaning": "red", "forms": ["rojo"]}]}, "at least one bank colour"),
    ({"articles": [{"agreement": "feminine", "text": "la"},
                   {"agreement": "feminine", "text": "las"}]}, "repeat an agreement"),
    ({"contractions": [{"preposition": "de", "article": "el", "text": "del"},
                       {"preposition": "De", "article": "El", "text": "Del"}]},
     "repeat a preposition and article"),
])
def test_clue_files_reject_incomplete_grammar(changes, message):
    with pytest.raises(ValidationError, match=message):
        CluesFile.model_validate(_clues(**changes))
    CluesFile.model_validate(_clues())
