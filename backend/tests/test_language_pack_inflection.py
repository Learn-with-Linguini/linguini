"""Bound words written with suffixes in suffixing languages (Korean particles, stem changes)."""

from pathlib import Path

from bundled_packs import bundled_pack

from app.language_packs.generation import ApprovedTerm, ApprovedVocabulary, _inflected_use

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"


def _vocabulary(fact_id, word):
    return ApprovedVocabulary(terms=[ApprovedTerm(
        term_id=fact_id.replace(":", "-"), fact_id=fact_id, source_text="thing",
        target_text=word, forms=[word], forms_by_key={"bare": word},
        part_of_speech="noun", provenance="sessionTranslation",
    )])


def test_korean_particles_attach_to_the_bound_noun():
    language = bundled_pack(PACKS / "ko-KR" / "everyday").language
    assert language.inflection == "suffixing"
    vocabulary = _vocabulary("object:cup", "컵")
    for text, surface in (("컵이에요?", "컵이에요"), ("컵을 찾아보세요.", "컵을"),
                          ("컵이 탁자 위에 있어요.", "컵이")):
        use = _inflected_use(text, vocabulary, "object:cup", "noun", language)
        assert use is not None and use.surface == surface, text
    assert _inflected_use("책이에요?", vocabulary, "object:cup", "noun", language) is None


def test_stem_endings_and_minimum_stem_length():
    language = bundled_pack(PACKS / "ko-KR" / "everyday").language.model_copy(
        update={"stem_endings": ["um"]},
    )
    vocabulary = _vocabulary("object:datum", "datum")
    # The stem may lose a declared ending before a suffix (datum -> data-ka).
    assert _inflected_use("dataka?", vocabulary, "object:datum", "noun", language).surface == (
        "dataka"
    )
    # A stem never shrinks below two letters, and the word must extend it.
    short = _vocabulary("object:um", "aum")
    assert _inflected_use("ax?", short, "object:um", "noun", language) is None
    assert _inflected_use("dat?", vocabulary, "object:datum", "noun", language) is None


def test_modifier_forms_never_take_suffixes():
    language = bundled_pack(PACKS / "ko-KR" / "everyday").language
    red = ApprovedVocabulary(terms=[ApprovedTerm(
        term_id="red", fact_id="attribute:red", source_text="red", target_text="빨간색",
        forms=["빨간색", "빨간"], forms_by_key={"default": "빨간색", "modifier": "빨간"},
        part_of_speech="adjective", provenance="sessionTranslation",
    )])
    assert _inflected_use("빨간색이에요.", red, "attribute:red", "adjective", language)
    # 빨간 only precedes a noun: 빨간이에요 is not a form of the colour.
    assert _inflected_use("문은 빨간이에요.", red, "attribute:red", "adjective", language) is None


def test_languages_without_suffixing_keep_whole_word_matching():
    language = bundled_pack(PACKS / "es-ES" / "everyday").language
    assert language.inflection == "none"
    vocabulary = _vocabulary("object:cup", "taza")
    assert _inflected_use("¿Es una tazas?", vocabulary, "object:cup", "noun", language) is None
