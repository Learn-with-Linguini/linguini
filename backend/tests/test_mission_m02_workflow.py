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
from app.services import mission_eligibility

A1_ES = {"proficiency_level": "A1", "target_language_code": "es"}


@pytest.fixture(autouse=True)
def existing_a1_missions(monkeypatch):
    """Keep legacy mission workflows independent of the newly added M04/M05 variants."""
    monkeypatch.setitem(
        mission_eligibility.IMPLEMENTED_MISSIONS,
        "A1",
        (("M01", "A1", 1), ("M02", "A1", 1), ("M03", "A1", 1)),
    )


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


def test_one_relation_plans_one_m02_task_with_the_three_core_questions(curated):
    engine, _owner, profile, client, *_ = curated
    model = SceneModel()
    repository, sid, detail = _lesson(curated, _relations_only, model)
    assert _planned(detail) == ["M02"]
    introduction, lesson, *bonus = detail.tasks
    assert introduction.kind == "vocabularyIntroduction"
    assert [lesson] == _parts(detail)
    assert bonus and {task.kind for task in bonus} <= {"ispyRound", "reflection"}
    assert not any("m02" in name for name in model.requests)
    content = lesson.public_content
    assert content.title == "Find and locate" and content.explanation is None
    choose, describe, ask = content.questions
    assert choose.prompt == "Elige la posición: la taza ___ la mesa."
    assert choose.prompt_translation == "Choose the position: the cup ___ the table."
    assert (choose.object_label, choose.reference_label) == ("Cup", "Table")
    assert choose.scene_object_id and choose.reference_object_id
    assert describe.scene_object_id == choose.scene_object_id
    assert describe.prompt == "Describe la posición de la taza."
    assert ask.reference_object_id is None
    assert (ask.prompt, ask.prompt_translation) == (
        "Pregunta por la ubicación de la taza.", "Ask where the cup is.",
    )
    key = _answer_key(engine, lesson.id)
    assert key["correctOptionIds"]["describe-location"] == "La taza está sobre la mesa."
    assert key["correctOptionIds"]["ask-where"] == "¿Dónde está la taza?"
    assert [item["targetIds"] for item in key["questionEvaluations"]] == [
        ["recognise-position"], ["describe-location", "name-object"],
        ["build-question", "name-object"],
    ]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public
    draft = _scalar(engine, select(sessions.c.analysis_draft).where(sessions.c.id == sid))
    assert draft["missionPlan"] == [
        {"missionId": "M02", "practiceLevel": "A1", "contentVersion": 1}
    ]
    resumed = repository.get(sid, profile.id)
    assert [t.public_content for t in _parts(resumed)] == [content]


@pytest.mark.parametrize("scenario", ["correct", "incorrect"])
def test_m02_is_graded_once_across_its_questions(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated, _relations_only)
    (task,) = _parts(detail)
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    correct = _correct_answers(engine, task)
    answers = {}
    for question in task.public_content.questions:
        right = correct[question.question_id]
        wrong = next(
            (o.option_id for o in question.options if o.option_id != right),
            "mesa la sobre está taza La .",
        )
        answers[question.question_id] = right if scenario == "correct" else wrong
    first = _attempt(client, task, answers, key=f"m02-{task.id}")
    assert first.status_code == 200, first.text
    awarded = _scalar(engine, xp)
    repeat = _attempt(client, task, answers, key=f"m02-{task.id}")
    assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
    assert _scalar(engine, xp) == awarded
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == task.id
    )) == 1
    details = first.json()["attempt"]["evaluationDetails"]
    assert details["questionResults"] == {qid: scenario == "correct" for qid in answers}
    saved = client.get(f"/api/v1/tasks/{task.id}/latest-attempt").json()["attempt"]
    assert saved["answers"] == answers
    assert saved["reviewDetails"]["questionResults"] == details["questionResults"]
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    assert len(outcomes) == len(answers) == 3
    for question in task.public_content.questions:
        outcome = outcomes[question.question_id]
        if question.interaction_type == "sentenceBuilding":
            assert outcome["evidenceType"] == "construction"
            assert outcome["assistance"] == ["wordBank"]
    if scenario == "incorrect":
        assert outcomes["choose-position"]["mistakes"][0]["mistake"] == "wrongPosition"


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
