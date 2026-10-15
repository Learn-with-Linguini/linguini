"""M01 A1 eligibility, reviewed colour forms and the deterministic lesson."""

from types import SimpleNamespace

import pytest

from app.ai.features.learning_tasks.mission_m01 import (
    M01LessonResult,
    fallback_m01_lesson,
    validate_m01_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import agreed_colour, lesson_missions, photo_eligibility
from app.services.mission_lessons_m01 import m01_payload

MISSION = get_mission("M01", "A1", 2)
CUP = "11111111-1111-1111-1111-111111111111"
BOOK = "22222222-2222-2222-2222-222222222222"
TABLE = "33333333-3333-3333-3333-333333333333"


def obj(label, **attributes):
    return SimpleNamespace(label=label, attributes=attributes or None)


def payload(language="fr"):
    pairs = [
        dict(key=CUP, source="cup", nounPhrase="une tasse", colourKey=f"{CUP}:color",
             colourSource="red", agreedForm="rouge", vocabularyItemId=CUP),
        dict(key=BOOK, source="book", nounPhrase="un livre", colourKey=f"{BOOK}:color",
             colourSource="green", agreedForm="vert", vocabularyItemId=BOOK),
    ]
    return {
        "targetLanguage": language, "missionId": "M01", "practiceLevel": "A1",
        "contentVersion": 2, "pairs": pairs,
        "distractors": {CUP: ["un livre", "une table"], BOOK: ["une tasse"]},
        "identifyPrompt": "Qu'est-ce que c'est ?", "describePrompt": "Décris cet objet.",
        "sentenceStart": "C'est",
        "example": "C'est une table blanche.",
    }


def word(item_id, text, gender):
    return SimpleNamespace(id=item_id, display_text=text, gender=gender)


def scene_object(item_id, label, colour):
    return SimpleNamespace(id=item_id, label=label, attributes={"color": colour})


@pytest.mark.parametrize(("objects", "reasons"), [
    ([obj("cup", color="red"), obj("book", color="green")], ()),
    ([obj("cup", color="red"), obj("Cup ", color="blue")], (
        "Confirm at least 2 different objects.",
        "Confirm the colours of at least 2 different objects.",
    )),
    ([obj("cup", color="red"), obj("book", material="paper")], (
        "Confirm the colours of at least 2 different objects.",
    )),
    ([obj("cup", color="sparkly"), obj("book", color="green")], (
        "Confirm the colours of at least 2 different objects.",
    )),
])
def test_eligibility_uses_only_confirmed_names_and_reviewed_colours(objects, reasons):
    result = photo_eligibility(MISSION, objects)
    assert (result.eligible, result.reasons) == (not reasons, reasons)


def test_colour_forms_agree_only_when_the_gender_is_known():
    assert agreed_colour("red", "es", "feminine") == "roja"
    assert agreed_colour("green", "fr", "feminine") == "verte"
    assert agreed_colour("blue", "es", None) == "azul"
    assert agreed_colour("red", "es", None) is None
    assert agreed_colour("red", "de", "masculine") is None


@pytest.mark.parametrize(("mode", "level", "language", "selected"), [
    ("lesson", "A1", "es", True),
    ("lesson", "A1", "fr", True),
    ("lesson", "A0", "es", False),
    ("lesson", "A2", "es", False),
    ("lesson", "A1", "de", False),
    ("ispyGame", "A1", "es", False),
])
def test_mission_path_needs_an_a1_lesson_in_a_supported_language(
    mode, level, language, selected,
):
    profile = {"proficiency_level": level, "target_language_code": language}
    assert bool(lesson_missions(mode, profile)) is selected


def test_fallback_identifies_then_describes_each_object_in_french():
    result = fallback_m01_lesson(payload())
    questions = result.questions
    assert [(q.purpose, q.object_key) for q in questions] == [
        ("identifyObject", CUP), ("describeObject", CUP),
        ("identifyObject", BOOK), ("describeObject", BOOK),
    ]
    assert questions[0].prompt == "Qu'est-ce que c'est ?"
    labels = {o.option_id: o.label for o in questions[0].options}
    assert sorted(labels.values()) == ["Un livre", "Une table", "Une tasse"]
    assert labels[questions[0].correct_option_id] == "Une tasse"
    assert [o.label for o in questions[2].options] == ["Un livre", "Une tasse"]
    assert questions[1].correct_text == "C'est une tasse rouge."
    assert questions[3].correct_text == "C'est un livre vert."
    assert sorted(questions[3].token_bank) == sorted(["C'", "est", "un", "livre", "vert", "."])
    assert "rouge" not in result.explanation and "vert" not in result.explanation


def test_pairs_prefer_unfamiliar_words_and_spanish_uses_indefinite_articles():
    mission = MISSION
    objects = [scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "green"),
               scene_object(TABLE, "table", "white")]
    words = [word(CUP, "taza", "feminine"), word(BOOK, "libro", "masculine"),
             word(TABLE, "mesa", "feminine")]
    unseen = m01_payload(mission, "es", objects, words, None, {})
    assert [p["source"] for p in unseen["pairs"]] == ["cup", "book"]
    progress = {"objects": {CUP: 0.9}, "terms": {"verde": 1.0},
                "taught_nouns": [{"text": "el gato", "gender": "masculine"}]}
    chosen = m01_payload(mission, "es", objects, words, None, progress)
    assert [p["source"] for p in chosen["pairs"]] == ["table", "cup"]
    assert [p["nounPhrase"] for p in chosen["pairs"]] == ["una mesa", "una taza"]
    assert chosen["distractors"][TABLE] == ["una taza", "un libro", "un gato"]
    assert chosen["identifyPrompt"] == "¿Qué es esto?"
    lesson = fallback_m01_lesson(chosen)
    assert lesson.questions[1].correct_text == "Es una mesa blanca."


def test_a_single_usable_pair_builds_no_lesson():
    only = m01_payload(
        MISSION, "es", [scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "red")],
        [word(CUP, "taza", "feminine"), word(BOOK, "libro", None)], None, {},
    )
    assert len(only["pairs"]) == 1 and only["distractors"] == {}
    with pytest.raises(LearningTaskGenerationError):
        fallback_m01_lesson(only)


@pytest.mark.parametrize("change", [
    lambda data: data["questions"][1].update(correct_text="C'est une tasse verte."),
    lambda data: data["questions"][0].update(object_key=BOOK),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"][1].update(token_bank=["C'", "est", "une"]),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    data = fallback_m01_lesson(payload()).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m01_lesson(payload(), M01LessonResult.model_validate(data))
