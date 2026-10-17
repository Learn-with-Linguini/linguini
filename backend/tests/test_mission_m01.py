"""M01 A1 eligibility, reviewed colour forms and the deterministic lesson."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_m01 import (
    M01LessonResult,
    fallback_m01_lesson,
    validate_m01_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.schemas.tasks import SubmitVocabularyReviewAttemptRequest
from app.services.mission_eligibility import agreed_colour, lesson_missions, photo_eligibility
from app.services.mission_lessons_m01 import m01_lesson_task, m01_payload
from app.services.question_outcomes import review_details

DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least 2 different objects."
)
ONE_DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least one object."
)
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
        DETAIL_REASON,
    )),
    ([obj("cup", color="red"), obj("book", material="paper")], (
        DETAIL_REASON,
    )),
    ([obj("cup", color="sparkly"), obj("book", color="green")], (
        DETAIL_REASON,
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
    check_first, check_second, colour, describe = result.questions
    assert first["key"] != second["key"] and first["source"] != second["source"]
    assert [q.purpose for q in result.questions] == [
        "confirmObject", "confirmObject", "chooseAttribute", "describeObject",
    ]
    assert [q.question_id for q in result.questions[:2]] == ["confirm-first", "confirm-second"]
    assert [q.object_key for q in result.questions] == [
        first["key"], second["key"], first["key"], second["key"],
    ]
    assert [q.section for q in result.questions] == [
        "Task 1 · Identify objects in your photo", "Task 1 · Identify objects in your photo",
        "Task 2 · Describe them", "Task 2 · Describe them",
    ]
    assert all(q.translation is None for q in (check_first, check_second, colour))
    assert colour.attribute_keys == [first["attributeKey"]]
    assert describe.attribute_keys == [second["attributeKey"]]


@pytest.mark.parametrize(("index", "truth", "prompt", "right", "contrast"), [
    (0, True, "¿Es una taza?", "Sí, es una taza.", "No, es un libro."),
    (0, False, "¿Es un libro?", "No, es una taza.", "Sí, es un libro."),
    (1, True, "¿Es un libro?", "Sí, es un libro.", "No, es una taza."),
    (1, False, "¿Es una taza?", "No, es un libro.", "Sí, es una taza."),
])
def test_is_it_this_checks_answer_with_taught_chunks(index, truth, prompt, right, contrast):
    data = build("es")
    data["layout"]["statementCorrect"][index] = truth
    check = fallback_m01_lesson(data).questions[index]
    assert [pair["source"] for pair in data["pairs"]] == ["cup", "book"]
    assert check.statement_correct is truth
    assert check.prompt == prompt
    assert correct(check) == right
    assert set(labels(check)) == {right, contrast}


def test_statement_truths_are_drawn_independently_per_question():
    truths = {
        tuple(build("es", session_id=UUID(int=n))["layout"]["statementCorrect"])
        for n in range(40)
    }
    assert truths == {(True, True), (True, False), (False, True), (False, False)}


def test_french_statement_uses_oui_non_and_cest():
    data = build("fr")
    data["layout"]["statementCorrect"] = [True, False]
    check_first, check_second = fallback_m01_lesson(data).questions[:2]
    assert check_first.prompt == "Est-ce une tasse ?"
    assert correct(check_first) == "Oui, c'est une tasse."
    assert check_second.prompt == "Est-ce une tasse ?"
    assert set(labels(check_second)) == {"Non, c'est un livre.", "Oui, c'est une tasse."}


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
        tuple(labels(fallback_m01_lesson(build("es", session_id=UUID(int=n))).questions[2]))
        for n in range(12)
    }
    assert len(orders) > 1


def test_task_persists_statement_truth_privately_and_keeps_order():
    data = build("es")
    result = fallback_m01_lesson(data)
    task = m01_lesson_task(SESSION, MISSION, data, result, {CUP: CUP, BOOK: BOOK})
    questions = task.public_content.questions
    assert task.answer_key.statement_correct == dict(zip(
        ["confirm-first", "confirm-second"], data["layout"]["statementCorrect"], strict=True,
    ))
    assert "statementCorrect" not in task.public_content.model_dump_json(by_alias=True)
    assert [q.keep_option_order for q in questions] == [True, True, True, None]
    assert [q.object_label for q in questions[:2]] == [None, None]
    assert [str(q.scene_object_id) for q in questions] == [CUP, BOOK, CUP, BOOK]
    assert [o.label for o in questions[0].options] == labels(result.questions[0])
    assert questions[3].token_bank and "." not in questions[3].token_bank
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    assert [rule.mistake for rule in rules["describe-object"].corrections] == ["wordOrder"]
    data = build("fr")
    task = m01_lesson_task(SESSION, MISSION, data, fallback_m01_lesson(data), {})
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    gender = rules["describe-object"].corrections[0]
    assert (gender.mistake, gender.answers) == ("wrongGender", ["C'est un livre verte."])


def test_confirm_and_attribute_questions_have_specific_correct_feedback():
    data = build("es")
    result = fallback_m01_lesson(data)
    task = m01_lesson_task(SESSION, MISSION, data, result, {})
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}

    confirm = result.questions[0]
    pair = next(row for row in data["pairs"] if row["key"] == confirm.object_key)
    confirm_note = f"This is {pair['nounPhrase']} ({pair['source']})."
    confirm_evaluation = evaluations[confirm.question_id]
    assert confirm_evaluation.correct_note == confirm_note
    assert confirm_evaluation.corrections[0].note == confirm_note
    assert confirm_evaluation.corrections[0].explanation == (
        f"{'Yes' if confirm.statement_correct else 'No'} — this is "
        f"{pair['nounPhrase']} ({pair['source']})."
    )

    choose = result.questions[2]
    pair = next(row for row in data["pairs"] if row["key"] == choose.object_key)
    choose_evaluation = evaluations[choose.question_id]
    correct_note = f"This {pair['source']} is {pair['attributeSource']}: {pair['agreedForm']}."
    assert choose_evaluation.correct_note == correct_note
    assert data["attributeMeanings"][fold("Roja")] == "red"
    assert data["attributeMeanings"][fold("Verde")] == "green"
    assert data["attributeMeanings"][fold("Blanca")] == "white"
    for option in choose.options:
        if option.option_id == choose.correct_option_id:
            continue
        meaning = data["attributeMeanings"][fold(option.label)]
        rule = next(
            rule for rule in choose_evaluation.corrections if option.option_id in rule.answers
        )
        assert rule.note == f"“{option.label}” means {meaning}."
        assert rule.explanation == (
            f"“{option.label}” means {meaning}; this {pair['source']} is "
            f"{pair['attributeSource']}: {pair['agreedForm']}."
        )

    legacy_payload = {key: value for key, value in data.items() if key != "attributeMeanings"}
    legacy_task = m01_lesson_task(
        SESSION, MISSION, legacy_payload, result, {},
    )
    legacy_evaluation = next(
        item for item in legacy_task.answer_key.question_evaluations
        if item.question_id == choose.question_id
    )
    assert legacy_evaluation.corrections[0].note is None
    assert legacy_evaluation.corrections[0].explanation == correct_note
    assert evaluations[result.questions[3].question_id].correct_note is None


def test_m01_correct_outcomes_show_notes_only_for_other_attribute_options():
    data = build("es")
    result = fallback_m01_lesson(data)
    task = m01_lesson_task(SESSION, MISSION, data, result, {})
    confirm, choose = result.questions[0], result.questions[2]
    answers = {
        confirm.question_id: confirm.correct_option_id,
        choose.question_id: choose.correct_option_id,
    }
    details = review_details(
        task,
        SubmitVocabularyReviewAttemptRequest(answers=answers),
        {question_id: True for question_id in answers},
        {},
    )
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    confirm_evaluation = next(
        item for item in task.answer_key.question_evaluations
        if item.question_id == confirm.question_id
    )
    assert outcomes[confirm.question_id]["correctNote"] == confirm_evaluation.correct_note
    assert "optionNotes" not in outcomes[confirm.question_id]
    choose_evaluation = next(
        item for item in task.answer_key.question_evaluations
        if item.question_id == choose.question_id
    )
    expected_notes = [
        rule.note for rule in choose_evaluation.corrections
        if rule.note and rule.note != choose_evaluation.correct_note
    ]
    assert outcomes[choose.question_id]["optionNotes"] == expected_notes


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


@pytest.mark.parametrize("language", ["es", "fr"])
def test_catalog_genders_recorded_as_articles_still_agree(language):
    articles = {"es": ("la", "el", "la"), "fr": ("la", "le", "la")}[language]
    canonical = build(language)
    words = [word(item.id, item.display_text, article) for item, article in zip(
        {"fr": [word(CUP, "tasse", ""), word(BOOK, "livre", ""), word(TABLE, "table", "")],
         "es": [word(CUP, "taza", ""), word(BOOK, "libro", ""), word(TABLE, "mesa", "")]}[language],
        articles, strict=True,
    )]
    payload = build(language, words=words)
    assert payload["pairs"] == canonical["pairs"]
    validate_m01_lesson(payload, fallback_m01_lesson(payload))


def detailed(item_id, label, **attributes):
    return SimpleNamespace(id=item_id, label=label, attributes=attributes)


def test_other_confirmed_details_are_described_with_agreement_and_placement():
    objects = [detailed(CUP, "cup", color="red"), detailed(BOOK, "book", size="small"),
               detailed(TABLE, "table", color="green")]
    data = build("fr", objects=objects)
    first, second = data["pairs"]
    assert (first["attributeType"], second["attributeType"]) == ("colour", "size")
    describe = fallback_m01_lesson(data).questions[3]
    # French petit goes before the noun and agrees with it.
    assert describe.correct_text == "C'est un petit livre."
    assert describe.translation == "It's a small book."
    assert "petite" in describe.token_bank
    spanish = fallback_m01_lesson(build("es", objects=objects)).questions[3]
    assert spanish.correct_text == "Es un libro pequeño."


def test_second_object_prefers_a_non_colour_detail():
    objects = [detailed(CUP, "cup", color="red"),
               detailed(BOOK, "book", color="green", material="wooden"),
               detailed(TABLE, "table")]
    second = build("es", objects=objects)["pairs"][1]
    assert (second["attributeType"], second["agreedForm"]) == ("material", "de madera")
    describe = fallback_m01_lesson(build("es", objects=objects)).questions[3]
    assert describe.correct_text == "Es un libro de madera."


def test_detail_choice_uses_reviewed_contrasts_and_a_type_prompt():
    objects = [detailed(CUP, "cup", state="empty"), detailed(BOOK, "book", material="wood"),
               detailed(TABLE, "table")]
    data = build("es", objects=objects)
    choose = fallback_m01_lesson(data).questions[2]
    assert choose.purpose == "chooseAttribute"
    assert choose.prompt == "¿Cómo es?"
    assert correct(choose) == "Vacía"
    assert set(labels(choose)) == {"Vacía", "Llena"}
    task = m01_lesson_task(SESSION, MISSION, data, fallback_m01_lesson(data), {})
    shown = task.public_content.questions[2]
    assert shown.prompt_translation == "What is it like?"
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    assert rules["choose-attribute"].corrections[0].mistake == "wrongAttribute"


def test_details_without_reviewed_forms_or_contrasts_are_not_used():
    unknown = [detailed(CUP, "cup", material="velvet"), detailed(BOOK, "book", size="medium"),
               detailed(TABLE, "table")]
    assert build("es", objects=unknown)["pairs"] == []
    no_contrast = [detailed(CUP, "cup", pattern="striped"), detailed(BOOK, "book", state="open"),
                   detailed(TABLE, "table")]
    data = build("es", objects=no_contrast)
    assert [pair["attributeType"] for pair in data["pairs"]] == ["pattern", "state"]
    assert data["attributeOptions"] == ["de rayas", "de lunares"]
