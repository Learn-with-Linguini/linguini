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
from app.missions import get_mission
from app.services.mission_eligibility import photo_eligibility, plan_missions
from app.services.mission_lessons_m02 import m02_lesson_task, m02_payload

M01 = get_mission("M01", "A1", 1)
M02 = get_mission("M02", "A1", 1)
CUP, BOOK, TABLE = uuid4(), uuid4(), uuid4()


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
    return m02_payload(M02, language, objects, relations, words, scene, progress)


def _relation(payload, index):
    keys = {row["key"]: row for row in payload["relations"]}
    return keys[payload["selected"][index]]


def test_review_relation_keys_get_their_reviewed_answer():
    (relation,) = _payload(relations=[rel(CUP, "inFrontOf", BOOK)])["relations"]
    assert relation["statement"] == "La tasse est devant le livre."
    assert relation["answer"] == "Elle est devant le livre."


def test_statement_groups_the_contracted_position_into_one_tile():
    (relation,) = _payload()["relations"]
    assert relation["statementTiles"] == ["La", "tasse", "est", "à côté du", "livre", "."]
    assert relation["statement"] == "La tasse est à côté du livre."
    (spanish,) = _payload("es")["relations"]
    assert spanish["statement"] == "La taza está al lado del libro."
    assert spanish["answer"] == "Está al lado del libro."
    assert spanish["whereQuestion"] == "¿Dónde está la taza?"


def test_one_relation_gives_only_the_three_core_questions():
    payload = _payload()
    assert len(payload["selected"]) == 1
    result = fallback_m02_lesson(payload)
    assert [q.purpose for q in result.questions] == [
        "choosePosition", "describeLocation", "askWhere",
    ]


def test_more_objects_without_another_relation_add_no_check():
    same = [rel(CUP, "on", TABLE), rel(CUP, "on", TABLE)]
    assert len(_payload("es", same)["selected"]) == 1


def test_task_two_prefers_another_pair_and_unfamiliar_phrases_come_first():
    relations = [rel(CUP, "on", TABLE), rel(BOOK, "under", TABLE)]
    unseen = _payload("es", relations)
    assert [_relation(unseen, i)["position"] for i in (0, 1)] == ["on", "under"]
    familiar = _payload("es", relations, {"terms": {"sobre": 0.9}})
    assert [_relation(familiar, i)["position"] for i in (0, 1)] == ["under", "on"]


def _numbered(subject, relation, reference, number):
    made = rel(subject, relation, reference)
    made.id = UUID(int=number)
    return made


def test_fallback_builds_core_questions_and_a_true_check_from_confirmed_facts():
    relations = [_numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "under", TABLE, 4)]
    result = fallback_m02_lesson(_payload("es", relations))
    assert [q.purpose for q in result.questions] == [
        "choosePosition", "describeLocation", "askWhere", "checkAnswer",
    ]
    choose, describe, ask, check = result.questions
    assert choose.prompt == "Elige la posición: la taza ___ la mesa."
    assert describe.prompt == "Describe la posición de la taza."
    assert ask.prompt == "Pregunta por la ubicación de la taza."
    labels = {o.option_id: o.label for o in choose.options}
    assert labels[choose.correct_option_id] == "sobre"
    assert set(labels.values()) == {"sobre", "debajo de", "al lado de"}
    assert describe.correct_text == "La taza está sobre la mesa."
    assert sorted(describe.token_bank) == sorted(
        ["La", "taza", "está", "sobre", "la", "mesa", ".", "debajo de"]
    )
    assert ask.correct_text == "¿Dónde está la taza?"
    assert check.prompt == "\u201cEl libro está debajo de la mesa.\u201d ¿Coincide con la foto?"
    assert {o.option_id: o.label for o in check.options} == {"yes": "Sí", "no": "No"}
    assert check.correct_option_id == "yes" and check.object_key == str(BOOK)


def test_position_choices_have_short_notes_and_correct_answers_have_correct_notes():
    payload = _payload("es", [
        _numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "under", TABLE, 4),
    ])
    result = fallback_m02_lesson(payload)
    task = m02_lesson_task(uuid4(), M02, payload, result, {})
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
    choose, _, _, check = result.questions
    choose_evaluation = evaluations[choose.question_id]
    relation = next(row for row in payload["relations"] if row["key"] == choose.relation_key)
    position = next(
        row for row in payload["positions"] if row["position"] == relation["position"]
    )
    correct_note = (
        f"The {relation['subjectSource']} is {position['meaning']} "
        f"the {relation['referenceSource']}."
    )
    assert choose_evaluation.correct_note == correct_note
    for option in choose.options:
        if option.option_id == choose.correct_option_id:
            continue
        phrase = next(row for row in payload["positions"] if row["expression"] == option.label)
        rule = next(
            rule for rule in choose_evaluation.corrections if option.option_id in rule.answers
        )
        assert rule.note == f"“{phrase['expression']}” means {phrase['meaning']}."
        assert rule.explanation == (
            f"“{phrase['expression']}” means {phrase['meaning']}; "
            f"{correct_note[0].lower()}{correct_note[1:]}"
        )

    check_evaluation = evaluations[check.question_id]
    check_relation = next(
        row for row in payload["relations"] if row["key"] == check.relation_key
    )
    assert check_evaluation.correct_note == f"The photo shows: {check_relation['statement']}"
    assert all(rule.note is None for rule in check_evaluation.corrections)


def test_a_wrong_proposal_uses_the_position_the_photo_contradicts():
    relations = [_numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "under", TABLE, 3)]
    check = fallback_m02_lesson(_payload("es", relations)).questions[3]
    assert check.prompt == "\u201cEl libro está sobre la mesa.\u201d ¿Coincide con la foto?"
    assert check.correct_option_id == "no"


def test_next_to_has_no_contradicting_position_so_its_proposal_is_true():
    relations = [_numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "next_to", TABLE, 3)]
    check = fallback_m02_lesson(_payload("es", relations)).questions[3]
    assert "El libro está al lado de la mesa." in check.prompt
    assert check.correct_option_id == "yes"


def test_french_prompts_are_in_french_and_never_contain_the_built_sentence():
    relations = [_numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "under", TABLE, 4)]
    choose, describe, ask, check = fallback_m02_lesson(_payload("fr", relations)).questions
    assert choose.prompt == "Choisis la position : la tasse ___ la table."
    assert describe.prompt == "Décris la position de la tasse."
    assert ask.prompt == "Pose une question sur l'emplacement de la tasse."
    assert check.prompt == (
        "\u00ab Le livre est sous la table. \u00bb Est-ce que ça correspond à la photo ?"
    )
    assert {o.label for o in check.options} == {"Oui", "Non"}
    for question in (describe, ask):
        assert question.correct_text.casefold() not in question.prompt.casefold()


def test_inverse_relations_are_not_offered_as_wrong_phrases():
    payload = _payload("es", [rel(CUP, "next_to", BOOK), rel(BOOK, "under", CUP)])
    choose = fallback_m02_lesson(payload).questions[0]
    assert {o.label for o in choose.options} == {"al lado de", "debajo de", "delante de"}


@pytest.mark.parametrize("change", [
    lambda data: data["questions"][0].update(correct_option_id="phrase-9"),
    lambda data: data["questions"][3].update(correct_option_id="no"),
    lambda data: data["questions"][3].update(prompt="¿Coincide con la foto?"),
    lambda data: data["questions"].pop(3),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"][1].update(token_bank=["La", "tasse"]),
    lambda data: data["questions"][2].update(correct_text="Où est le livre ?"),
    lambda data: data["questions"][1].update(relation_key="other"),
    lambda data: data["questions"].pop(2),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    payload = _payload("fr", [_numbered(CUP, "on", TABLE, 2), _numbered(BOOK, "under", TABLE, 4)])
    data = fallback_m02_lesson(payload).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m02_lesson(payload, M02LessonResult.model_validate(data))
