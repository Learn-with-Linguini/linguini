"""Multiple-mission lessons on a confirmed scene: planning, M02 grading and completion."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_mission_m01_workflow import (
    _analyzed,
    _answer_key,
    _attempt,
    _colours,
    _repository,
    _review,
    _scalar,
)
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, services
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import task_attempts
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.enums import SessionMode
from app.schemas.sessions import ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest

A1_ES = {"proficiency_level": "A1", "target_language_code": "es"}


def _relations_only(detail):
    return ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in detail.scene_objects],
        relations=detail.scene_object_relations,
    )


def _colours_only(detail):
    return ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in detail.scene_objects],
        object_attributes=_colours(detail),
    )


def _without_clue_model(curated, model):
    """The scripted clue model needs a colour and a relation; partial scenes use fallbacks."""
    engine, owner, *_ = curated
    feature = services(model)
    return PostgresWorkflowRepository(
        engine, owner.id, translator=feature["translation"],
        learning_task_generator=feature["lessons"],
    )


def _lesson(curated, review=_review, model=None):
    profile = curated[2]
    model = model or SceneModel()
    repository = (
        _repository(curated, model) if review is _review else _without_clue_model(curated, model)
    )
    sid, analyzed = _analyzed(curated, repository)
    repository.review(sid, profile.id, review(analyzed))
    return repository, sid, repository.get(sid, profile.id)


def _planned(detail):
    return list(dict.fromkeys(task.public_content.mission_id for task in detail.tasks
                              if task.public_content.mission_id))


def _correct_answers(engine, task):
    return _answer_key(engine, task.id)["correctOptionIds"]


def test_colour_only_scene_plans_m01(curated):
    _repository_, _sid, detail = _lesson(curated, _colours_only)
    assert _planned(detail) == ["M01"]


def _parts(detail):
    return [task for task in detail.tasks if task.public_content.mission_id == "M02"]


def test_relation_only_scene_plans_four_m02_parts_after_the_shared_vocabulary(curated):
    engine, _owner, profile, client, *_ = curated
    model = SceneModel()
    repository, sid, detail = _lesson(curated, _relations_only, model)
    assert _planned(detail) == ["M02"]
    introduction, *rest = detail.tasks
    parts, bonus = rest[:4], rest[4:]
    assert introduction.kind == "vocabularyIntroduction"
    assert parts == _parts(detail)
    assert bonus and {task.kind for task in bonus} <= {"ispyRound", "reflection"}
    assert not any("m02" in name for name in model.requests)
    assert [task.public_content.title for task in parts] == [
        "Describe the location · Part 1 of 2", "Describe the location · Part 2 of 2",
        "Ask and understand · Part 1 of 2", "Ask and understand · Part 2 of 2",
    ]
    choose, describe, ask, understand = (task.public_content.questions[0] for task in parts)
    assert choose.prompt == "Where is the cup in relation to the table?"
    assert (choose.object_label, choose.reference_label) == ("Cup", "Table")
    assert choose.scene_object_id and choose.reference_object_id
    assert describe.scene_object_id == choose.scene_object_id
    assert ask.reference_object_id is None and ask.prompt == "Ask where the cup is."
    assert understand.scene_object_id is None and understand.diagram_options is True
    assert "Está sobre la mesa." in understand.prompt
    keys = [_answer_key(engine, task.id) for task in parts]
    assert keys[1]["correctOptionIds"]["describe-location"] == "La taza está sobre la mesa."
    assert keys[2]["correctOptionIds"]["ask-where"] == "¿Dónde está la taza?"
    assert keys[3]["correctOptionIds"]["understand-answer"] == "on"
    assert [key["questionEvaluations"][0]["targetIds"] for key in keys] == [
        ["recognise-position"], ["describe-location", "name-object"],
        ["build-question", "name-object"], ["understand-location"],
    ]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public
    draft = _scalar(engine, select(sessions.c.analysis_draft).where(sessions.c.id == sid))
    assert draft["missionPlan"] == [
        {"missionId": "M02", "practiceLevel": "A1", "contentVersion": 2}
    ]
    resumed = repository.get(sid, profile.id)
    assert [t.public_content for t in _parts(resumed)] == [t.public_content for t in parts]


@pytest.mark.parametrize("scenario", ["correct", "incorrect"])
def test_each_m02_part_is_graded_once(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated, _relations_only)
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    for task in _parts(detail):
        question = task.public_content.questions[0]
        correct = _correct_answers(engine, task)[question.question_id]
        wrong = next(
            (o.option_id for o in question.options if o.option_id != correct),
            "mesa la sobre está taza La .",
        )
        answer = {question.question_id: correct if scenario == "correct" else wrong}
        first = _attempt(client, task, answer, key=f"m02-{task.id}")
        assert first.status_code == 200, first.text
        awarded = _scalar(engine, xp)
        repeat = _attempt(client, task, answer, key=f"m02-{task.id}")
        assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
        assert _scalar(engine, xp) == awarded
        assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
            task_attempts.c.session_task_id == task.id
        )) == 1
        details = first.json()["attempt"]["evaluationDetails"]
        assert details["questionResults"] == {question.question_id: scenario == "correct"}
        saved = client.get(f"/api/v1/tasks/{task.id}/latest-attempt").json()["attempt"]
        assert saved["answers"] == answer
        assert saved["reviewDetails"]["questionResults"] == details["questionResults"]
        (outcome,) = details["questionOutcomes"]
        if question.interaction_type == "sentenceBuilding":
            assert outcome["evidenceType"] == "construction"
            assert outcome["assistance"] == ["wordBank"]
        elif scenario == "incorrect":
            assert outcome["mistakes"][0]["mistake"] == "wrongPosition"


def test_a_photo_fitting_both_plans_both_and_the_lesson_finishes_after_both(curated):
    engine, _owner, profile, client, *_ = curated
    repository, sid, detail = _lesson(curated)
    assert _planned(detail) == ["M01", "M02"]
    kinds = [task.kind for task in detail.tasks]
    assert kinds[:3] == ["vocabularyIntroduction", "grammarLesson", "grammarLesson"]
    assert "ispyRound" in kinds[3:]
    m01, m02 = detail.tasks[1], _parts(detail)[0]
    assert m01.id != m02.id and m01.order_index < m02.order_index
    answered = _attempt(client, m01, _correct_answers(engine, m01), key="both-missions")
    assert answered.status_code == 200, answered.text
    repository.task_action(detail.tasks[0].id, "skip", SkipTaskRequest())
    with pytest.raises(PracticeConflictError):
        repository.finish(sid, profile.id)
    for task in detail.tasks[2:]:
        repository.task_action(task.id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted",
    )) == 1


def test_a_photo_no_mission_supports_gets_the_regular_lesson_and_tips_for_each(curated):
    profile = curated[2]
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    repository.review(sid, profile.id, ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in analyzed.scene_objects]
    ))
    detail = repository.get(sid, profile.id)
    tips = " ".join(detail.mission_guidance)
    assert "Identify and describe an object: Confirm the colour" in tips
    assert "Find and locate: Confirm where one object is" in tips
    assert detail.session.analysis_draft["missionPlan"] == []
    assert all(task.public_content.mission_key is None for task in detail.tasks)


def test_sessions_saved_before_mission_plans_keep_the_regular_lesson(curated):
    repository = _repository(curated, SceneModel())
    lesson = SessionMode.LESSON

    def planned(draft):
        session = SimpleNamespace(mode=lesson, analysis_draft=draft)
        return [m.mission_id for m in repository._planned_missions(session, A1_ES)]

    assert planned({}) == []
    assert planned({"missionPlan": []}) == []
    assert planned({"missionPlan": [
        {"missionId": "M02", "practiceLevel": "A1", "contentVersion": 1}
    ]}) == ["M02"]
