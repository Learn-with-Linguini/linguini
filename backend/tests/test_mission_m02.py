"""Multiple-mission planning, per-mission photo eligibility and the M02 A1 lesson."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.ai.features.learning_tasks.mission_m02 import (
    M02LessonResult,
    fallback_m02_lesson,
    validate_m02_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import definition_file_name, get_mission
from app.services.mission_eligibility import photo_eligibility, plan_missions
from app.services.mission_lessons_m02 import m02_lesson_task, m02_payload
from app.services.question_outcomes import normalize_answer

M01 = get_mission("M01", "A1", 1)
M02 = get_mission("M02", "A1", 2)
CUP = UUID("33333333-0000-0000-0000-000000000000")
BOOK = UUID("11111111-0000-0000-0000-000000000000")
TABLE = UUID("22222222-0000-0000-0000-000000000000")
SESSION = UUID("44444444-4444-4444-4444-444444444444")


def obj(id, label, **attributes):
    return SimpleNamespace(id=id, label=label, attributes=attributes or None)


def rel(subject, relation, reference):
    return SimpleNamespace(
        id=uuid4(), subject_scene_object_id=subject, relation=relation,
        reference_scene_object_id=reference,
    )


COLOURED = [obj(CUP, "cup", color="red"), obj(BOOK, "book", color="blue")]
PLAIN = [obj(CUP, "cup"), obj(BOOK, "book")]
ON = [rel(CUP, "on", BOOK)]


@pytest.mark.parametrize(("objects", "relations", "m01", "m02"), [
    (COLOURED, [], True, False),
    (PLAIN, ON, False, True),
    (COLOURED, ON, True, True),
    (PLAIN, [], False, False),
    (PLAIN, [rel(CUP, "inside", BOOK)], False, False),
    (PLAIN, [rel(CUP, "nextTo", BOOK)], False, True),
    (PLAIN, [rel(CUP, "inFrontOf", BOOK)], False, True),
    ([obj(CUP, "cup"), obj(BOOK, "Cup ")], ON, False, False),
])
def test_each_mission_checks_only_the_facts_it_needs(objects, relations, m01, m02):
    assert photo_eligibility(M01, objects, relations).eligible is m01
    assert photo_eligibility(M02, objects, relations).eligible is m02


def test_missing_relations_are_named_for_m02_only():
    assert photo_eligibility(M02, PLAIN, []).reasons == (
        "Confirm where one object is on, under, next to, in front of or behind another.",
    )
    assert photo_eligibility(M01, PLAIN, []).reasons == (
        "Confirm the colours of at least 2 different objects.",
    )


@pytest.mark.parametrize(("objects", "relations", "planned"), [
    (COLOURED, [], ["M01"]),
    (PLAIN, ON, ["M02"]),
    (COLOURED, ON, ["M01", "M02"]),
    (PLAIN, [], []),
])
def test_every_mission_the_photo_fits_is_planned(objects, relations, planned):
    plan = plan_missions([M01, M02], objects, relations)
    assert [mission.mission_id for mission in plan] == planned


def _payload(language="fr", relations=None, progress=None):
    objects = [obj(CUP, "cup"), obj(BOOK, "book"), obj(TABLE, "table")]
    words = [
        SimpleNamespace(display_text="tasse", gender="feminine"),
        SimpleNamespace(display_text="livre", gender="masculine"),
        SimpleNamespace(display_text="table", gender="feminine"),
    ] if language == "fr" else [
        SimpleNamespace(display_text="taza", gender="feminine"),
        SimpleNamespace(display_text="libro", gender="masculine"),
        SimpleNamespace(display_text="mesa", gender="feminine"),
    ]
    articles = {"fr": ("la", "le", "la"), "es": ("la", "el", "la")}[language]
    scene = SimpleNamespace(objects=[
        SimpleNamespace(key=str(key), article=article, gender=gender)
        for key, article, gender in zip(
            (CUP, BOOK, TABLE), articles, ("feminine", "masculine", "feminine"), strict=True,
        )
    ])
    relations = relations if relations is not None else [rel(CUP, "next_to", BOOK)]
    return m02_payload(M02, language, objects, relations, words, scene, progress, SESSION)


def _relation(payload):
    keys = {row["key"]: row for row in payload["relations"]}
    return keys[payload["selected"][0]]


def _labels(question):
    return {option.option_id: option.label for option in question.options}


def test_saved_version_one_lessons_still_resolve_their_definition():
    old = get_mission("M02", "A1", 1)
    assert old is not None and old.expected_performance.min_assessed_questions == 3
    assert M02.expected_performance.min_assessed_questions == 4
    assert definition_file_name(old) == "M02-A1.toml"
    assert definition_file_name(M02) == "M02-A1-2.toml"


def test_statement_groups_the_contracted_position_into_one_tile():
    relation = _relation(_payload())
    assert relation["statementTiles"] == ["La", "tasse", "est", "à côté du", "livre", "."]
    assert relation["statement"] == "La tasse est à côté du livre."
    spanish = _relation(_payload("es"))
    assert spanish["statement"] == "La taza está al lado del libro."
    assert spanish["whereQuestion"] == "¿Dónde está la taza?"


def test_one_relation_is_selected_even_when_more_are_confirmed():
    relations = [rel(CUP, "on", TABLE), rel(BOOK, "under", TABLE)]
    payload = _payload("es", relations)
    assert len(payload["relations"]) == 2 and len(payload["selected"]) == 1
    familiar = _payload("es", relations, {"terms": {"sobre": 1.0}})
    assert _relation(familiar)["position"] == "under"


@pytest.mark.parametrize("language", ["es", "fr"])
def test_all_four_questions_reuse_the_one_confirmed_relation(language):
    payload = _payload(language, [rel(CUP, "on", TABLE)])
    result = fallback_m02_lesson(payload)
    relation = _relation(payload)
    assert [q.purpose for q in result.questions] == [
        "findObject", "chooseLocation", "askWhere", "answerWhere",
    ]
    assert {(q.relation_key, q.object_key) for q in result.questions} == {
        (relation["key"], str(CUP)),
    }
    find, choose, ask, answer = result.questions
    expected = {
        "es": ("La taza está sobre la mesa.", "¿Dónde está la taza?"),
        "fr": ("La tasse est sur la table.", "Où est la tasse ?"),
    }[language]
    assert (find.prompt, choose.prompt) == expected
    assert (answer.correct_text, ask.correct_text) == expected
    assert all(q.translation is None for q in (find, choose))


def test_marker_question_picks_the_subject_with_scene_review_numbers():
    payload = _payload("es", [rel(CUP, "on", TABLE)])
    find = fallback_m02_lesson(payload).questions[0]
    # Markers follow the confirmed objects in ID order: book 1, table 2, cup 3.
    assert payload["markers"] == [
        dict(key=str(BOOK), marker=1, source="book"),
        dict(key=str(TABLE), marker=2, source="table"),
        dict(key=str(CUP), marker=3, source="cup"),
    ]
    assert _labels(find) == {"marker-1": "1", "marker-2": "2", "marker-3": "3"}
    assert find.marker_keys == {
        "marker-1": str(BOOK), "marker-2": str(TABLE), "marker-3": str(CUP),
    }
    assert find.correct_option_id == "marker-3"


def test_objects_named_like_the_subject_are_never_marker_distractors():
    objects = [obj(CUP, "cup"), obj(BOOK, "cup"), obj(TABLE, "table")]
    words = [SimpleNamespace(display_text=text, gender="feminine")
             for text in ("taza", "taza", "mesa")]
    scene = SimpleNamespace(objects=[
        SimpleNamespace(key=str(key), article="la", gender="feminine")
        for key in (CUP, BOOK, TABLE)
    ])
    payload = m02_payload(M02, "es", objects, [rel(CUP, "on", TABLE)], words, scene, None, SESSION)
    assert _relation(payload)["markerOptions"] == [str(CUP), str(TABLE)]


def test_location_options_are_taught_with_only_the_confirmed_one_true():
    payload = _payload("es", [rel(CUP, "on", TABLE), rel(TABLE, "next_to", CUP)])
    choose = fallback_m02_lesson(payload).questions[1]
    labels = _labels(choose)
    assert labels[choose.correct_option_id] == "sobre la mesa"
    assert "al lado de la mesa" not in labels.values()
    assert set(labels.values()) <= {
        "sobre la mesa", "debajo de la mesa", "delante de la mesa", "detrás de la mesa",
    }
    assert "debajo de la mesa" in labels.values()


def test_answer_tiles_offer_a_contradicting_position_that_is_rejected():
    payload = _payload("fr", [rel(CUP, "on", TABLE)])
    result = fallback_m02_lesson(payload)
    answer = result.questions[3]
    relation = _relation(payload)
    assert relation["answerExtra"] == "sous"
    assert relation["contradiction"] == "La tasse est sous la table."
    assert sorted(answer.token_bank) == sorted(["La", "tasse", "est", "sur", "la", "table", ".",
                                                "sous"])
    task = m02_lesson_task(SESSION, M02, payload, result, {})
    rules = {e.question_id: e for e in task.answer_key.question_evaluations}
    wrong = rules["answer-where"].corrections[0]
    assert (wrong.mistake, wrong.answers) == ("wrongPosition", ["La tasse est sous la table."])


def test_task_shows_markers_without_highlight_then_highlights_both_objects():
    payload = _payload("es", [rel(CUP, "on", TABLE)])
    result = fallback_m02_lesson(payload)
    questions = m02_lesson_task(SESSION, M02, payload, result, {}).public_content.questions
    find, choose, ask, answer = questions
    assert find.scene_object_id is None and find.reference_object_id is None
    assert {k: str(v) for k, v in find.marker_object_ids.items()} == result.questions[0].marker_keys
    assert (choose.scene_object_id, choose.reference_object_id) == (CUP, TABLE)
    assert (answer.scene_object_id, answer.reference_object_id) == (CUP, TABLE)
    assert [q.keep_option_order for q in questions] == [True, True, None, None]
    assert [q.section for q in questions] == [
        "Task 1 · Find it in your photo", "Task 1 · Find it in your photo",
        "Task 2 · Ask and answer where", "Task 2 · Ask and answer where",
    ]


def test_option_order_is_stable_for_a_session():
    relations = [rel(CUP, "on", TABLE)]
    one = fallback_m02_lesson(_payload("es", relations)).questions[1]
    two = fallback_m02_lesson(_payload("es", relations)).questions[1]
    assert [o.label for o in one.options] == [o.label for o in two.options]


def test_removed_objects_drop_their_relations():
    payload = _payload("es", [rel(CUP, "on", uuid4())])
    assert payload["relations"] == [] and payload["selected"] == []


def _mutate(result, index, **changes):
    questions = list(result.questions)
    questions[index] = questions[index].model_copy(update=changes)
    return result.model_copy(update={"questions": questions})


@pytest.mark.parametrize("change", [
    lambda r: _mutate(r, 0, correct_option_id="marker-2"),
    lambda r: _mutate(r, 0, marker_keys={**r.questions[0].marker_keys, "marker-1": str(uuid4())}),
    lambda r: _mutate(r, 0, options=[o.model_copy(update={"label": "9"})
                                     if o.option_id == "marker-1" else o
                                     for o in r.questions[0].options]),
    lambda r: _mutate(r, 0, prompt="La taza está debajo de la mesa."),
    lambda r: _mutate(r, 1, options=[o.model_copy(update={"label": "al lado de la mesa"})
                                     if o.option_id != r.questions[1].correct_option_id else o
                                     for o in r.questions[1].options][:2]),
    lambda r: _mutate(r, 3, correct_text="La taza está debajo de la mesa."),
    lambda r: _mutate(r, 2, token_bank=[*r.questions[2].token_bank, "libro"]),
    lambda r: _mutate(r, 1, relation_key=str(uuid4())),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    payload = _payload("es", [rel(CUP, "on", TABLE), rel(TABLE, "next_to", CUP)])
    result = fallback_m02_lesson(payload)
    with pytest.raises((LearningTaskGenerationError, ValueError)):
        validate_m02_lesson(payload, M02LessonResult.model_validate(
            change(result).model_dump(by_alias=True)
        ))


def test_built_french_questions_match_their_spaced_question_mark():
    ask = fallback_m02_lesson(_payload("fr", [rel(CUP, "on", TABLE)])).questions[2]
    assert ask.correct_text == "Où est la tasse ?"
    assert normalize_answer("Où est la tasse?") == normalize_answer(ask.correct_text)
