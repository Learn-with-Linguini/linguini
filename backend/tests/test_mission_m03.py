"""M03 A1 counted-group eligibility, three-mission planning, quantities and the lesson."""

import re
from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_m03 import (
    M03LessonResult,
    fallback_m03_lesson,
    validate_m03_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.schemas.sessions import ReviewPracticeRequest
from app.services.mission_eligibility import photo_eligibility, plan_missions
from app.services.mission_lessons_m03 import m03_lesson_task, m03_payload
from app.services.quantities import (
    NUMBER_WORDS,
    regular_plural,
    suggested_quantity,
    taught_numbers,
    wrong_quantities,
)

M01, M02, M03 = (get_mission(mission_id, "A1", 1) for mission_id in ("M01", "M02", "M03"))
CUP, BOOK = uuid4(), uuid4()
TAUGHT_ES = {NUMBER_WORDS["es"][n] for n in range(2, 11)}
TAUGHT_FR = {NUMBER_WORDS["fr"][n] for n in range(2, 11)}


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None,
                           bounding_box={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})


def counted(quantity, ids=(BOOK,), label="book", suggested=None):
    return {"sceneObjectIds": [str(item) for item in ids], "label": label,
            "quantity": quantity, "suggestedQuantity": suggested, "source": "entered"}


ON = [SimpleNamespace(
    id=uuid4(), subject_scene_object_id=CUP, relation="on", reference_scene_object_id=BOOK,
)]
FULL = [obj(CUP, "cup", color="red"), obj(BOOK, "book", color="blue")]


@pytest.mark.parametrize(("groups", "eligible"), [
    ([], False), ([counted(1)], False), ([counted(2)], True), ([counted(10)], True),
])
def test_m03_needs_a_counted_group_of_two_to_ten(groups, eligible):
    result = photo_eligibility(M03, [obj(BOOK, "book")], [], groups)
    assert result.eligible is eligible
    if not eligible:
        assert result.reasons == ("Count a group of 2 to 10 matching objects.",)


def test_a_count_alone_never_satisfies_m01_or_m02():
    objects, groups = [obj(BOOK, "book")], [counted(3)]
    assert not photo_eligibility(M01, objects, [], groups).eligible
    assert not photo_eligibility(M02, objects, [], groups).eligible


@pytest.mark.parametrize(("objects", "relations", "groups", "planned"), [
    ([obj(BOOK, "book")], [], [counted(3)], ["M03"]),
    (FULL, ON, [counted(3)], ["M01", "M02", "M03"]),
    (FULL, ON, [counted(1)], ["M01", "M02"]),
    (FULL, [], [counted(3)], ["M01", "M03"]),
])
def test_every_mission_the_photo_fits_is_planned_up_to_three(objects, relations, groups, planned):
    plan = plan_missions([M01, M02, M03], objects, relations, groups)
    assert [mission.mission_id for mission in plan] == planned


@pytest.mark.parametrize(("value", "expected"), [
    ("3", 3), ("three", 3), (" Two books", 2), ("10", 10), ("11", None), ("0", None),
    ("several", None), ("", None), (None, None), (3, None),
])
def test_only_a_one_to_ten_quantity_is_suggested(value, expected):
    assert suggested_quantity(value) == expected


@pytest.mark.parametrize(("language", "noun", "plural"), [
    ("es", "libro", "libros"), ("es", "taza", "tazas"), ("es", "flor", "flores"),
    ("es", "pared", "paredes"), ("es", "lápiz", None), ("es", "examen", None),
    ("es", "camión", None), ("es", "papel higiénico", None),
    ("fr", "livre", "livres"), ("fr", "tasse", "tasses"), ("fr", "cheval", None),
    ("fr", "bateau", None), ("fr", "bijou", None), ("fr", "nez", None), ("de", "Buch", None),
])
def test_only_reviewed_regular_plurals_are_produced(language, noun, plural):
    assert regular_plural(language, noun) == plural


def test_wrong_quantities_are_nearby_and_within_range():
    assert wrong_quantities(3, 2, 10) == [4, 2, 5]
    assert wrong_quantities(10, 2, 10) == [9, 8, 7]
    assert wrong_quantities(2, 2, 10) == [3, 4, 5]


def test_taught_numbers_default_to_the_mission_range():
    numbers, source = taught_numbers(M03, {})
    assert numbers == tuple(range(2, 11)) and source == "missionDefault"


@pytest.mark.parametrize(("progress", "numbers", "source"), [
    ({"taught_number_range": (2, 20)}, tuple(range(2, 21)), "learnerRecords"),
    ({"taught_number_range": (2, 3)}, (2, 3), "learnerRecords"),
    ({"taught_number_range": (0, 30)}, tuple(range(2, 21)), "learnerRecords"),
    ({"taught_number_range": [5]}, tuple(range(2, 11)), "missionDefault"),
])
def test_an_explicit_range_widens_taught_numbers(progress, numbers, source):
    assert taught_numbers(M03, progress) == (numbers, source)


@pytest.mark.parametrize("quantity", [0, 11])
def test_review_rejects_out_of_range_counts(quantity):
    with pytest.raises(ValidationError):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={BOOK: quantity})


def test_review_rejects_counts_for_unselected_objects():
    with pytest.raises(ValidationError, match="Counts must reference selected objects"):
        ReviewPracticeRequest(accepted_object_ids=[BOOK], object_counts={CUP: 3})


def _scene(*entries):
    return SimpleNamespace(objects=[
        SimpleNamespace(key=str(key), gender=gender) for key, gender in entries
    ])


def _payload(language="es", quantity=3, display="libro", gender="masculine",
             plural_form=None, groups=None, progress=None, session_id=None, label="book",
             translated=None):
    words = [SimpleNamespace(display_text=display, plural_form=plural_form, gender=gender)]
    return m03_payload(
        M03, language, [obj(BOOK, label)], [], words,
        _scene((BOOK, gender)) if translated is None else translated,
        [counted(quantity)] if groups is None else groups,
        progress, session_id if session_id is not None else uuid4(),
    )


def _choose(result):
    return result.questions[0]


def _build(result):
    return result.questions[1]


def _match(result):
    return result.questions[2]


def _correct_option(question):
    return next(option for option in question.options
                if option.option_id == question.correct_option_id)


def test_the_lesson_is_three_questions_in_order_without_an_explanation():
    result = fallback_m03_lesson(_payload())
    assert result.title == "Say how many"
    assert not hasattr(result, "explanation")
    assert [q.purpose for q in result.questions] == [
        "chooseQuantity", "buildQuantity", "matchQuantity",
    ]
    assert [q.interaction_type for q in result.questions] == [
        "multipleChoice", "sentenceBuilding", "multipleChoice",
    ]
    assert [q.section for q in result.questions] == [
        "Task 1 · Count in your photo", "Task 1 · Count in your photo",
        "Task 2 · Practice board",
    ]


@pytest.mark.parametrize("suggested", [None, 2])
def test_choose_answers_with_the_learners_count_not_the_suggestion(suggested):
    payload = _payload(quantity=3, groups=[counted(3, suggested=suggested)])
    result = fallback_m03_lesson(payload)
    assert _correct_option(_choose(result)).label == "tres"


def test_choose_options_are_few_distinct_taught_number_words():
    for session_id in [uuid4() for _ in range(6)]:
        for language, display, taught in (
            ("es", "libro", TAUGHT_ES), ("fr", "livre", TAUGHT_FR),
        ):
            result = fallback_m03_lesson(_payload(
                language, display=display, session_id=session_id,
            ))
            choose = _choose(result)
            labels = [option.label for option in choose.options]
            assert 2 <= len(labels) <= 3
            assert len(set(labels)) == len(labels)
            assert set(labels) <= taught
            assert not any(re.search(r"\d", label) for label in labels)
            assert choose.correct_option_id in {option.option_id for option in choose.options}
            assert len({option.option_id for option in choose.options}) == len(labels)


@pytest.mark.parametrize(("language", "display", "gender", "statement"), [
    ("es", "taza", "feminine", "Hay tres tazas."),
    ("fr", "tasse", "feminine", "Il y a trois tasses."),
])
def test_build_uses_the_plural_and_a_bank_with_one_wrong_number(
    language, display, gender, statement,
):
    payload = _payload(language, display=display, gender=gender, label="cup")
    build = _build(fallback_m03_lesson(payload))
    assert build.correct_text == statement
    assert build.translation is None
    extras = Counter(map(fold, build.token_bank)) - Counter(map(fold, tokens(statement)))
    assert extras[fold(display)] == 1
    (wrong,) = [token for token in extras if token != fold(display)]
    words = {fold(word) for word in NUMBER_WORDS[language].values()}
    assert wrong in words and wrong != "tres"


@pytest.mark.parametrize(("display", "gender", "question"), [
    ("libro", "masculine", "¿Cuántos libros hay?"),
    ("taza", "feminine", "¿Cuántas tazas hay?"),
])
def test_spanish_how_many_agrees_with_the_nouns_gender(display, gender, question):
    payload = _payload(display=display, gender=gender)
    assert payload["group"]["question"] == question


def test_spanish_skips_a_group_whose_noun_gender_is_unknown():
    payload = _payload(display="libro", gender=None, translated=_scene((BOOK, None)))
    assert payload["group"] is None


@pytest.mark.parametrize(("display", "question"), [
    ("livre", "Combien de livres y a-t-il ?"),
    ("orange", "Combien d'oranges y a-t-il ?"),
    ("épée", "Combien d'épées y a-t-il ?"),
])
def test_french_how_many_elides_before_a_vowel(display, question):
    payload = _payload("fr", display=display)
    assert payload["group"]["question"] == question


def test_french_skips_an_h_initial_noun():
    payload = _payload("fr", display="haricot")
    assert payload["group"] is None


def test_the_board_targets_a_quantity_above_the_photo_count():
    payload = _payload(quantity=3)
    match = _match(fallback_m03_lesson(payload))
    counts = match.board_counts
    assert set(counts) == {option.option_id for option in match.options}
    assert len(set(counts.values())) == len(counts)
    assert counts[match.correct_option_id] > 3
    assert match.prompt.endswith(f" {payload['group']['plural']}.")
    assert match.quantity_word == NUMBER_WORDS["es"][counts[match.correct_option_id]]
    assert match.board_object_id == str(BOOK)
    assert [option.label for option in match.options] == [
        f"Board {letter}" for letter in "ABC"[:len(match.options)]
    ]
    assert not any(re.search(r"\d", option.label) for option in match.options)


def test_a_count_of_ten_boards_another_taught_quantity():
    match = _match(fallback_m03_lesson(_payload(quantity=10)))
    assert match.board_counts[match.correct_option_id] != 10
    assert all(count in range(2, 11) for count in match.board_counts.values())


def test_an_explicit_taught_range_allows_boards_above_ten():
    targets = set()
    for _ in range(12):
        match = _match(fallback_m03_lesson(_payload(
            progress={"taught_number_range": (2, 20)}, session_id=uuid4(),
        )))
        targets.add(match.board_counts[match.correct_option_id])
        assert all(count in range(2, 21) for count in match.board_counts.values())
    assert any(target > 10 for target in targets)


def test_a_two_number_range_leaves_two_options_everywhere():
    result = fallback_m03_lesson(_payload(progress={"taught_number_range": (2, 3)}))
    assert len(_choose(result).options) == 2
    assert len(_match(result).options) == 2
    match = _match(result)
    assert set(match.board_counts.values()) == {2, 3}
    assert match.board_counts[match.correct_option_id] == 2


def test_the_lesson_is_deterministic_for_a_session():
    session_id = uuid4()
    first = fallback_m03_lesson(_payload(session_id=session_id)).model_dump()
    second = fallback_m03_lesson(_payload(session_id=session_id)).model_dump()
    assert first == second
    positions = set()
    for _ in range(8):
        choose = _choose(fallback_m03_lesson(_payload(session_id=uuid4())))
        positions.add(
            next(index for index, option in enumerate(choose.options)
                 if option.option_id == choose.correct_option_id)
        )
    assert positions != {0}


@pytest.mark.parametrize("payload", [
    lambda: _payload(display="lápiz"),
    lambda: _payload(plural_form="libritos"),
    lambda: _payload(groups=[]),
    lambda: _payload(groups=[counted(1)]),
    lambda: _payload(groups=[counted(3, ids=(uuid4(),))]),
])
def test_unreviewed_plurals_and_unconfirmed_groups_have_no_lesson(payload):
    payload = payload()
    assert payload["group"] is None
    with pytest.raises(LearningTaskGenerationError):
        fallback_m03_lesson(payload)


def test_validator_rejects_reordered_or_missing_questions():
    payload = _payload()
    for change in (
        lambda data: data["questions"].reverse(),
        lambda data: data["questions"].pop(),
        lambda data: data["questions"].append(dict(data["questions"][0])),
    ):
        data = fallback_m03_lesson(payload).model_dump()
        change(data)
        with pytest.raises((ValueError, LearningTaskGenerationError)):
            validate_m03_lesson(payload, M03LessonResult.model_validate(data))


def test_validator_rejects_a_wrong_build_or_board():
    payload = _payload()
    for change in (
        lambda data: data["questions"][1].update(correct_text="Hay cuatro libros."),
        lambda data: data["questions"][1].update(token_bank=["Hay", "tres", "libros", "."]),
        lambda data: data["questions"][1].update(translation="There are three books."),
        lambda data: data["questions"][2].update(board_counts={"board-a": 3, "board-b": 3}),
        lambda data: data["questions"][2].update(quantity_word="cuatro"),
    ):
        data = fallback_m03_lesson(payload).model_dump()
        change(data)
        with pytest.raises((ValueError, LearningTaskGenerationError)):
            validate_m03_lesson(payload, M03LessonResult.model_validate(data))


def test_corrections_separate_quantity_from_plural_mistakes():
    payload = _payload()
    result = fallback_m03_lesson(payload)
    task = m03_lesson_task(uuid4(), M03, payload, result, {str(BOOK): uuid4()})
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
    choose, build, match = result.questions
    by_answer = {
        option.option_id: [
            rule.mistake for rule in evaluations[choose.question_id].corrections
            if option.option_id in rule.answers
        ]
        for option in choose.options if option.option_id != choose.correct_option_id
    }
    assert all(mistakes == ["wrongQuantity"] for mistakes in by_answer.values())
    inverse_numbers = {
        fold(word): number for number, word in NUMBER_WORDS["es"].items()
    }
    for option in choose.options:
        if option.option_id == choose.correct_option_id:
            continue
        rule = next(
            rule for rule in evaluations[choose.question_id].corrections
            if option.option_id in rule.answers
        )
        assert rule.explanation == (
            f"“{option.label}” means {inverse_numbers[fold(option.label)]}; "
            "you counted 3: tres."
        )
    rules = {rule.mistake: rule.answers for rule in evaluations[build.question_id].corrections}
    assert "Hay tres libro." in rules["pluralForm"]
    assert "Hay tres libros." not in rules["pluralForm"]
    assert "Hay cuatro libros." in rules["wrongQuantity"]
    assert rules["wordOrder"] == []
    match_rules = evaluations[match.question_id].corrections
    target = match.board_counts[match.correct_option_id]
    assert all(
        rule.mistake == "wrongQuantity" and f"means {target}." in rule.explanation
        for rule in match_rules
    )
    assert [item.evidence_type for item in task.answer_key.question_evaluations] == [
        "recognition", "construction", "recognition",
    ]
    build_eval = evaluations[build.question_id]
    assert len(build_eval.vocabulary_item_ids) == 1
    assert evaluations[choose.question_id].vocabulary_item_ids == []
    assert evaluations[match.question_id].vocabulary_item_ids == []
