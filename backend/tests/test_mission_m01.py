"""M01 A1 eligibility, reviewed colour forms and the deterministic lesson."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.features.learning_tasks.mission_m01 import (
    M01LessonResult,
    fallback_m01_lesson,
    validate_m01_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import agreed_colour, lesson_missions, photo_eligibility
from app.services.mission_lessons_m01 import m01_lesson_task, m01_payload

MISSION = get_mission("M01", "A1", 1)
CUP = "11111111-1111-1111-1111-111111111111"
BOOK = "22222222-2222-2222-2222-222222222222"
TABLE = "33333333-3333-3333-3333-333333333333"


def obj(label, **attributes):
    return SimpleNamespace(label=label, attributes=attributes or None)


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
    # A0 is the stored level for "I'm a complete beginner" (pre-A1).
    ("lesson", "A0", "es", False),
    ("lesson", "A0", "fr", False),
    ("lesson", "A2", "es", False),
    ("lesson", "B1", "fr", False),
    ("lesson", None, "es", False),
    ("lesson", "A1", "de", False),
    ("ispyGame", "A1", "es", False),
])
def test_mission_path_needs_an_a1_lesson_in_a_supported_language(
    mode, level, language, selected,
):
    profile = {"proficiency_level": level, "target_language_code": language}
    assert bool(lesson_missions(mode, profile)) is selected


SESSION = UUID("44444444-4444-4444-4444-444444444444")


def build(language="fr", objects=None, words=None, progress=None, session_id=SESSION):
    objects = objects or [
        scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "green"),
        scene_object(TABLE, "table", "white"),
    ]
    words = words or {
        "fr": [word(CUP, "tasse", "feminine"), word(BOOK, "livre", "masculine"),
               word(TABLE, "table", "feminine")],
        "es": [word(CUP, "taza", "feminine"), word(BOOK, "libro", "masculine"),
               word(TABLE, "mesa", "feminine")],
    }[language]
    return m01_payload(MISSION, language, objects, words, None, progress, session_id)


def labels(question):
    return [option.label for option in question.options]


def correct(question):
    return next(o.label for o in question.options if o.option_id == question.correct_option_id)


@pytest.mark.parametrize("language", ["fr", "es"])
def test_two_tasks_ask_four_questions_about_two_different_confirmed_objects(language):
    data = build(language)
    result = fallback_m01_lesson(data)
    first, second = data["pairs"]
    identify, confirm, colour, describe = result.questions
    assert first["key"] != second["key"] and first["source"] != second["source"]
    assert [q.purpose for q in result.questions] == [
        "identifyObject", "confirmObject", "chooseColour", "describeObject",
    ]
    assert [q.object_key for q in result.questions] == [
        first["key"], second["key"], first["key"], second["key"],
    ]
    assert [q.section for q in result.questions] == [
        "Task 1 · Identify objects in your photo", "Task 1 · Identify objects in your photo",
        "Task 2 · Describe their colours", "Task 2 · Describe their colours",
    ]
    assert identify.prompt == {"fr": "Qu'est-ce que c'est ?", "es": "¿Qué es esto?"}[language]
    assert correct(identify).casefold() == first["nounPhrase"]
    assert all(q.translation is None for q in (identify, confirm, colour))
    assert colour.attribute_keys == [first["colourKey"]]
    assert describe.attribute_keys == [second["colourKey"]]


def test_identification_options_are_taught_nouns_with_exactly_one_correct():
    data = build("es")
    identify = fallback_m01_lesson(data).questions[0]
    assert {label.casefold() for label in labels(identify)} <= set(data["taughtNouns"])
    assert sorted(label.casefold() for label in labels(identify)) == [
        "un libro", "una mesa", "una taza",
    ]
    assert [o.label.casefold() for o in identify.options].count(
        data["pairs"][0]["nounPhrase"]
    ) == 1


@pytest.mark.parametrize(("truth", "prompt", "right", "contrast"), [
    (True, "¿Es un libro?", "Sí, es un libro.", "No, es una taza."),
    (False, "¿Es una taza?", "No, es un libro.", "Sí, es una taza."),
])
def test_yes_no_statement_answers_with_taught_chunks(truth, prompt, right, contrast):
    data = build("es")
    data["layout"]["statementCorrect"] = truth
    confirm = fallback_m01_lesson(data).questions[1]
    assert data["pairs"][1]["source"] == "book"
    assert confirm.statement_correct is truth
    assert confirm.prompt == prompt
    assert correct(confirm) == right
    assert set(labels(confirm)) == {right, contrast}


def test_french_statement_uses_oui_non_and_cest():
    data = build("fr")
    data["layout"]["statementCorrect"] = False
    confirm = fallback_m01_lesson(data).questions[1]
    assert confirm.prompt == "Est-ce une tasse ?"
    assert set(labels(confirm)) == {"Non, c'est un livre.", "Oui, c'est une tasse."}


def test_colour_options_agree_and_skip_visually_similar_colours():
    objects = [
        scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "green"),
        scene_object(TABLE, "table", "pink"),
    ]
    data = build("es", objects=objects, progress={"terms": {"azules": 1.0, "negra": 0.5}})
    colour = fallback_m01_lesson(data).questions[2]
    assert correct(colour) == "Roja"
    assert "Rosa" not in labels(colour)
    assert set(labels(colour)) <= {"Roja", "Verde", "Negra", "Azul"}
    assert len(labels(colour)) == len(set(labels(colour)))


def test_description_has_article_noun_then_agreed_colour_and_a_wrong_gender_tile():
    objects = [scene_object(CUP, "cup", "green"), scene_object(BOOK, "book", "red")]
    words = [word(CUP, "libro", "masculine"), word(BOOK, "taza", "feminine")]
    data = build("es", objects=objects, words=words)
    describe = fallback_m01_lesson(data).questions[3]
    assert describe.correct_text == "Es una taza roja."
    assert sorted(describe.token_bank) == sorted(["Es", "una", "taza", "roja", ".", "rojo"])
    data = build("fr")
    describe = fallback_m01_lesson(data).questions[3]
    assert describe.correct_text == "C'est un livre vert."
    assert "verte" in describe.token_bank


def test_option_order_is_shuffled_per_session_and_stable_on_rebuild():
    one = fallback_m01_lesson(build("es"))
    again = fallback_m01_lesson(build("es"))
    assert [labels(q) for q in one.questions] == [labels(q) for q in again.questions]
    orders = {
        tuple(labels(fallback_m01_lesson(build("es", session_id=UUID(int=n))).questions[0]))
        for n in range(12)
    }
    assert len(orders) > 1


def test_task_persists_statement_truth_privately_and_keeps_order():
    data = build("es")
    result = fallback_m01_lesson(data)
    task = m01_lesson_task(SESSION, MISSION, data, result, {CUP: CUP, BOOK: BOOK})
    questions = task.public_content.questions
    assert task.answer_key.statement_correct == {"confirm-object": data["layout"][
        "statementCorrect"
    ]}
    assert "statementCorrect" not in task.public_content.model_dump_json(by_alias=True)
    assert [q.keep_option_order for q in questions] == [True, True, True, None]
    assert [q.object_label for q in questions[:2]] == [None, None]
    assert [str(q.scene_object_id) for q in questions] == [CUP, BOOK, CUP, BOOK]
    assert [o.label for o in questions[0].options] == labels(result.questions[0])
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    assert [rule.mistake for rule in rules["describe-object"].corrections] == ["wordOrder"]
    data = build("fr")
    task = m01_lesson_task(SESSION, MISSION, data, fallback_m01_lesson(data), {})
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    gender = rules["describe-object"].corrections[0]
    assert (gender.mistake, gender.answers) == ("wrongGender", ["C'est un livre verte."])


def test_unconfirmed_or_removed_objects_are_never_used():
    objects = [scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "sparkly")]
    words = [word(CUP, "taza", "feminine"), word(BOOK, "libro", "masculine")]
    assert build("es", objects=objects, words=words)["pairs"] == []
    objects = [scene_object(CUP, "cup", "red"), scene_object(BOOK, "Cup", "green")]
    assert build("es", objects=objects, words=words)["pairs"] == []


def test_pairs_prefer_unfamiliar_words_and_spanish_uses_indefinite_articles():
    progress = {"objects": {CUP: 0.9}, "terms": {}}
    data = build("es", progress=progress)
    assert [pair["source"] for pair in data["pairs"]] == ["book", "table"]
    assert [pair["nounPhrase"] for pair in data["pairs"]] == ["un libro", "una mesa"]


def test_no_clearly_different_colour_builds_no_lesson():
    objects = [scene_object(CUP, "cup", "red"), scene_object(BOOK, "book", "pink")]
    words = [word(CUP, "taza", "feminine"), word(BOOK, "libro", "masculine")]
    assert build("es", objects=objects, words=words)["pairs"] == []


def _mutate(result, index, **changes):
    questions = list(result.questions)
    questions[index] = questions[index].model_copy(update=changes)
    return result.model_copy(update={"questions": questions})


@pytest.mark.parametrize("change", [
    lambda r: _mutate(r, 1, object_key=CUP),
    lambda r: _mutate(r, 0, options=[*r.questions[0].options[:-1], r.questions[0].options[
        -1
    ].model_copy(update={"label": "Une chaise"})]),
    lambda r: _mutate(r, 0, translation="It's a cup."),
    lambda r: _mutate(r, 1, statement_correct=not r.questions[1].statement_correct),
    lambda r: _mutate(r, 2, options=[o.model_copy(update={"label": "Rose"})
                                     if o.option_id != r.questions[2].correct_option_id else o
                                     for o in r.questions[2].options]),
    lambda r: _mutate(r, 3, correct_text="C'est un livre rouge."),
    lambda r: _mutate(r, 3, token_bank=[*r.questions[3].token_bank, "bleu"]),
    lambda r: r.model_copy(update={"questions": [r.questions[i] for i in (0, 2, 1, 3)]}),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    data = build("fr")
    result = fallback_m01_lesson(data)
    with pytest.raises((LearningTaskGenerationError, ValueError)):
        validate_m01_lesson(data, M01LessonResult.model_validate(
            change(result).model_dump(by_alias=True)
        ))
