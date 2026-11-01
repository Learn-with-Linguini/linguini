"""Bound prepositions written with a contracted article (à côté de + le = à côté du)."""

from pathlib import Path

from bundled_packs import bundled_pack

from app.language_packs.generation import ApprovedTerm, ApprovedVocabulary, _contracted_use

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"


def _vocabulary(fact_id, source, form):
    return ApprovedVocabulary(terms=[ApprovedTerm(
        term_id="model-contrast-1", fact_id=fact_id, source_text=source,
        target_text=form, forms=[form], forms_by_key={"bare": form},
        part_of_speech="preposition", provenance="sessionTranslation",
    )])


def test_french_preposition_accepts_its_listed_contractions():
    contractions = bundled_pack(PACKS / "fr-FR" / "everyday").clues.contractions
    vocabulary = _vocabulary("alternative:1", "next to", "à côté de")
    for text, surface in (("à côté du bureau", "à côté du"),
                          ("La tasse est à côté des livres.", "à côté des")):
        use = _contracted_use(text, vocabulary, "alternative:1", "preposition", contractions)
        assert use is not None and use.surface == surface, text
        assert use.term_id == "model-contrast-1"


def test_spanish_preposition_accepts_del():
    contractions = bundled_pack(PACKS / "es-ES" / "everyday").clues.contractions
    vocabulary = _vocabulary("alternative:1", "next to", "al lado de")
    use = _contracted_use("al lado del sofá", vocabulary, "alternative:1", "preposition",
                          contractions)
    assert use is not None and use.surface == "al lado del"


def test_contractions_never_stand_in_for_a_different_phrase_or_part_of_speech():
    contractions = bundled_pack(PACKS / "fr-FR" / "everyday").clues.contractions
    vocabulary = _vocabulary("alternative:1", "next to", "à côté de")
    # The rest of the phrase must still be written as reviewed.
    assert _contracted_use("près du bureau", vocabulary, "alternative:1", "preposition",
                           contractions) is None
    # A contraction the pack does not list is not accepted.
    assert _contracted_use("à côté dou bureau", vocabulary, "alternative:1", "preposition",
                           contractions) is None
    # Only prepositions are matched this way.
    assert _contracted_use("à côté du bureau", vocabulary, "alternative:1", "noun",
                           contractions) is None
    assert _contracted_use("à côté du bureau", vocabulary, "alternative:1", "preposition",
                           []) is None
