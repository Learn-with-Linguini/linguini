"""A1 M04 ownership mission eligibility, validation and lesson task tests."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.features.learning_tasks.mission_m04 import (
    M04LessonResult,
    fallback_m04_lesson,
    validate_m04_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import photo_eligibility
from app.services.mission_lessons_m04 import m04_lesson_task, m04_payload, m04_ready
from app.services.mission_roleplay import assign_roleplay

M04 = get_mission("M04", "A1", 1)


def _plural_answer(data):
    data["questions"][1]["correct_text"] = "Es mi libros."


def _add_excess_bank_tokens(data):
    data["questions"][1]["token_bank"].extend(["extra-one", "extra-two", "extra-three"])


def _payload(language="es", object_count=3):
    labels = ["book", "cup", "spoon"][:object_count]
    nouns = {
        "es": [("libro", "masculine"), ("taza", "feminine"), ("cuchara", "feminine")],
        "fr": [("livre", "masculine"), ("tasse", "feminine"), ("assiette", "feminine")],
    }[language][:object_count]
    objects = [
        SimpleNamespace(id=uuid4(), label=label, attributes=None)
        for label in labels
    ]
    words = [
        SimpleNamespace(display_text=noun, gender=gender)
        for noun, gender in nouns
    ]
    markers = {str(obj.id): index + 1 for index, obj in enumerate(objects)}
    session_id = uuid4()
    facts = assign_roleplay(M04, session_id, objects, markers)
    payload = m04_payload(
        M04,
        language,
        objects,
        words,
        SimpleNamespace(objects=[]),
        session_id,
        context={"roleplay_facts": facts, "review_markers": markers},
    )
    return payload, objects


@pytest.mark.parametrize("language", ["es", "fr"])
def test_m04_needs_three_distinct_confirmed_objects(language):
    payload, objects = _payload(language, object_count=2)
    assert photo_eligibility(M04, objects[:1]).eligible is False
    assert photo_eligibility(M04, objects).eligible is False
    assert payload["invalidRoleplay"] is True
    complete, complete_objects = _payload(language, object_count=3)
    assert photo_eligibility(M04, complete_objects).eligible is True
    assert complete["learner"]["sentence"]
    assert complete["ana"]["sentence"]
    assert complete["leo"]["sentence"]


def test_fallback_is_deterministic_and_passes_the_m04_validator():
    payload, _objects = _payload()
    first = fallback_m04_lesson(payload)
    second = fallback_m04_lesson(payload)
    assert first.model_dump() == second.model_dump()
    validate_m04_lesson(payload, first)
    purposes = [question.purpose for question in first.questions]
    assert not any(purpose.startswith("match") for purpose in purposes)
    assert purposes == ["chooseOwner", "buildMine", "buildTheirs"]
    assert [question.section for question in first.questions] == [
        "Task 1 · Whose is it?",
        "Task 2 · Say whose it is", "Task 2 · Say whose it is",
    ]


def test_choose_and_build_questions_use_the_assigned_facts_and_scoped_markers():
    payload, _objects = _payload(object_count=3)
    result = fallback_m04_lesson(payload)
    choose, mine, theirs = result.questions
    assert choose.markers == {payload["choice"]["objectKey"]: payload["choice"]["marker"]}
    correct_choice = next(
        option.label for option in choose.options
        if option.option_id == choose.correct_option_id
    )
    assert correct_choice == payload["leo"]["sentence"]
    assert correct_choice not in {mine.correct_text, theirs.correct_text}
    assert mine.markers == {payload["learner"]["objectKey"]: payload["learner"]["marker"]}
    assert theirs.markers == {payload["ana"]["objectKey"]: payload["ana"]["marker"]}


def test_public_task_keeps_fictional_facts_and_has_no_vocabulary_evaluations():
    payload, _objects = _payload()
    result = fallback_m04_lesson(payload)
    task = m04_lesson_task(uuid4(), M04, payload, result, {})
    task_content = task.public_content.model_dump(mode="json", by_alias=True)
    assert task_content["roleplayFacts"] == payload["facts"]
    assert task.public_content.questions[0].object_label
    assert all(question.marker_object_ids is None for question in task.public_content.questions)
    assert task.public_content.explanation.startswith(
        "For this practice, the owners are pretend."
    )
    assert [question.roleplay_premise for question in task.public_content.questions]
    assert all(
        not evaluation.vocabulary_item_ids
        for evaluation in task.answer_key.question_evaluations
    )
    for question in result.questions:
        if question.purpose.startswith("build"):
            assert question.translation is None
            assert question.correct_text


@pytest.mark.parametrize("mutation", [
    _plural_answer,
    _add_excess_bank_tokens,
])
def test_m04_validator_rejects_bad_build_forms_and_extra_bank_tokens(mutation):
    payload, _objects = _payload()
    result = fallback_m04_lesson(payload)
    data = result.model_dump(by_alias=False)
    mutation(data)
    invalid = M04LessonResult.model_validate(data)
    with pytest.raises(LearningTaskGenerationError):
        validate_m04_lesson(payload, invalid)


def test_m04_validator_rejects_inferred_facts_without_a_roleplay_premise():
    payload, _objects = _payload()
    result = fallback_m04_lesson(payload)
    invalid_payload = deepcopy(payload)
    invalid_payload["facts"][0]["source"] = "inferred"
    with pytest.raises(LearningTaskGenerationError, match="explicitly assigned"):
        validate_m04_lesson(invalid_payload, result)
    data = result.model_dump(by_alias=False)
    data["questions"][2]["roleplay_premise"] = ""
    with pytest.raises(ValueError):
        M04LessonResult.model_validate(data)


def test_m04_readiness_requires_leos_choice_and_build_sentences():
    payload, _objects = _payload()
    assert m04_ready(payload)
    for key in ("sentence", "contrast", "other_object_sentence"):
        missing = deepcopy(payload)
        missing["leo"][key] = None
        assert not m04_ready(missing)


def test_m04_questions_only_use_assigned_taught_forms():
    payload, _objects = _payload()
    result = fallback_m04_lesson(payload)
    choose, mine, theirs = result.questions
    assert {option.label for option in choose.options} == {
        payload["choice"][key]
        for key in ("sentence", "contrast", "other_object_sentence")
    }
    assert mine.correct_text == payload["learner"]["sentence"]
    assert theirs.correct_text == payload["ana"]["sentence"]
    assert sum(
        option.option_id == choose.correct_option_id for option in choose.options
    ) == 1
