"""A0 (pre-A1) scene missions: level gating, closed content and per-mission rules."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import (
    IMPLEMENTED_MISSIONS,
    lesson_missions,
    photo_eligibility,
)

WORDS = {
    "es": ["la taza", "el libro", "la manzana", "el árbol"],
    "fr": ["la tasse", "le livre", "la pomme", "l'arbre"],
    "de": ["die Tasse", "das Buch", "der Apfel", "der Baum"],
    "ko": ["컵", "책", "사과", "나무"],
}
LABELS = ["cup", "book", "apple", "tree"]
MISSIONS = ("M01", "M02", "M03", "M04", "M05", "M13")


def _objects(labels=LABELS):
    return [SimpleNamespace(id=uuid4(), label=label, attributes={}, bounding_box=None)
            for label in labels]






def _profile(level, language="es", **extra):
    return {"proficiency_level": level, "target_language_code": language, **extra}




@pytest.mark.parametrize("level", ["A1", "A2"])
def test_a1_and_a2_profiles_never_get_a0_missions(level):
    missions = lesson_missions(
        SessionMode.LESSON, _profile(level, onboarding_completed=False),
    )
    assert all(str(mission.practice_level) != "A0" for mission in missions)
    korean_missions = lesson_missions(SessionMode.LESSON, _profile(level, "ko"))
    # Korean gets every mission its pack has ready at the level.
    assert [mission.mission_id for mission in korean_missions] == (
        ["M01", "M02", "M03", "M04", "M06"] if level == "A2"
        else ["M01", "M02", "M03", "M04", "M05"]
    )


def test_a0_needs_a_lesson_and_a_stored_a0_level():
    assert lesson_missions(SessionMode.QUICK_REVIEW, _profile("A0")) if hasattr(
        SessionMode, "QUICK_REVIEW") else True
    for mode in SessionMode:
        if mode != SessionMode.LESSON:
            assert lesson_missions(mode, _profile("A0")) == []
    # The display label is never a stored level.
    assert lesson_missions(SessionMode.LESSON, _profile("Pre-A1")) == []
    assert "Pre-A1" not in IMPLEMENTED_MISSIONS














def _replace(result, position, question):
    questions = list(result.questions)
    questions[position] = question
    return result.model_copy(update={"questions": questions})




















def _groups(objects, *pairs):
    by_label = {obj.label: obj for obj in objects}
    return [
        {"label": label, "quantity": amount, "sceneObjectIds": [str(by_label[label].id)]}
        for label, amount in pairs
    ]


def test_m03_counts_the_first_valid_group_when_several_are_counted():
    mission = get_mission("M03", "A0", 1)
    objects = _objects(["cup", "book", "apple", "sofa"])
    several = _groups(objects, ("cup", 2), ("book", 2), ("apple", 3))
    assert photo_eligibility(mission, objects, [], several).eligible
    # Any confirmed name can be counted; an out-of-range group does not block a valid one.
    mixed = _groups(objects, ("sofa", 2), ("cup", 1), ("book", 4))
    assert photo_eligibility(mission, objects, [], mixed).eligible
    unusable = _groups(objects, ("cup", 1), ("book", 4))
    check = photo_eligibility(mission, objects, [], unusable)
    assert check.reasons == ("Count a group of 2 to 3 matching objects.",)
    assert check.missing == ("counts",)




def test_photo_eligibility_takes_any_two_differently_named_objects():
    mission = get_mission("M01", "A0", 1)
    # Packs teach whatever the learner confirmed, not a fixed noun list.
    assert photo_eligibility(mission, _objects(["cup", "sofa"]), []).eligible
    check = photo_eligibility(mission, _objects(["cup", "cup"]), [])
    assert check.reasons == ("Confirm at least 2 different objects.",)
    assert check.missing == ("objects",)




def _named_rows(*nouns):
    """Approved object rows with markers 1..n; repeated nouns are same-name objects."""
    return [dict(key=str(uuid4()), marker=number, noun=noun, label=noun)
            for number, noun in enumerate(nouns, 1)]


def _marker(rows, target):
    from app.ai.features.learning_tasks.mission_a0 import A0Question, marker_question

    payload = {"approvedObjects": rows, "approvedTranslations": {}}
    return A0Question.model_validate(
        marker_question(payload, "findNamed", "Task 1", target, "Busca el armario.", index=1)
    )


def _check(question, rows):
    from app.ai.features.learning_tasks.mission_a0 import _check_markers

    _check_markers(question, {option.option_id: option.label for option in question.options},
                   {row["key"]: row for row in rows})


def test_a_name_alone_accepts_every_marker_on_an_object_with_that_name():
    rows = _named_rows("armario", "ventana", "armario")
    question = _marker(rows, rows[2])
    assert question.correct_option_id == "marker-3"
    assert question.accepted_option_ids == ["marker-1"]
    _check(question, rows)
    # Leaving out a same-name marker would mark a right answer wrong.
    with pytest.raises(LearningTaskGenerationError, match="named word"):
        _check(question.model_copy(update={"accepted_option_ids": []}), rows)


def test_marker_choices_keep_a_differently_named_object():
    rows = _named_rows("armario", "armario", "armario", "ventana")
    question = _marker(rows, rows[0])
    assert [option.label for option in question.options] == ["1", "2", "4"]
    assert question.accepted_option_ids == ["marker-2"]
    _check(question, rows)


def test_distinct_names_accept_only_the_named_marker():
    rows = _named_rows("taza", "libro", "manzana")
    question = _marker(rows, rows[1])
    assert question.accepted_option_ids == []
    _check(question, rows)


def test_accepted_alternatives_grade_as_correct_and_stay_out_of_other_keys():
    from app.repositories.postgres.workflow import _lesson_answer_is_correct
    from app.schemas.tasks import TaskAnswerKey

    assert "acceptedOptionIds" not in TaskAnswerKey(
        correct_option_ids={"q": "marker-3"}
    ).model_dump(by_alias=True)
    task = SimpleNamespace(
        public_content=SimpleNamespace(questions=[
            SimpleNamespace(question_id="q", interaction_type="multipleChoice"),
        ]),
        answer_key=TaskAnswerKey(correct_option_ids={"q": "marker-3"},
                                 accepted_option_ids={"q": ["marker-1"]}),
    )
    assert _lesson_answer_is_correct(task, "q", "marker-3")
    assert _lesson_answer_is_correct(task, "q", "marker-1")
    assert not _lesson_answer_is_correct(task, "q", "marker-2")
