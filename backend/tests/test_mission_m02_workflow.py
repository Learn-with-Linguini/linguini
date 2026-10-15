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
from test_preloaded_templates import SceneModel, TextModelResponse, services
from test_preloaded_templates_workflow import curated as curated

from app.ai.features.learning_tasks import service as learning_service
from app.ai.features.learning_tasks.mission_m02 import (
    M02_PROMPT_VERSION,
    M02_SCHEMA_VERSION,
    fallback_m02_lesson,
)
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import task_attempts
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.enums import SessionMode
from app.schemas.sessions import ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest

A1_ES = {"proficiency_level": "A1", "target_language_code": "es"}


class M02Model(SceneModel):
    """Answers the M02 lesson request with valid content of its own."""

    def generate(self, request, **options):
        if request.json_schema_name != "mission_lesson_m02_v1":
            return super().generate(request, **options)
        self.requests.append(request.json_schema_name)
        result = fallback_m02_lesson(json.loads(request.user_content))
        body = result.model_copy(update={"title": "Model lesson"}).model_dump(
            mode="json", by_alias=True
        )
        return TextModelResponse(
            output_text=json.dumps(body), model_name="test-text-model",
            prompt_version=request.prompt_version, input_tokens=10, output_tokens=10,
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
    return [task.public_content.mission_id for task in detail.tasks
            if task.public_content.mission_id]


def _correct_answers(engine, task):
    return _answer_key(engine, task.id)["correctOptionIds"]


def test_colour_only_scene_plans_m01(curated):
    _repository_, _sid, detail = _lesson(curated, _colours_only)
    assert _planned(detail) == ["M01"]


def test_relation_only_scene_plans_m02_after_the_shared_vocabulary(curated):
    engine, _owner, _profile, client, *_ = curated
    model = SceneModel()
    _repository_, sid, detail = _lesson(curated, _relations_only, model)
    assert _planned(detail) == ["M02"]
    introduction, lesson, *bonus = detail.tasks
    assert introduction.kind == "vocabularyIntroduction"
    assert introduction.public_content.mission_key is None
    assert bonus and {task.kind for task in bonus} <= {"ispyRound", "reflection"}
    assert "mission_lesson_m02_v1" in model.requests
    assert lesson.public_content.title == "Ask where it is"
    questions = lesson.public_content.questions
    assert [q.interaction_type for q in questions] == [
        "multipleChoice", "sentenceBuilding", "multipleChoice",
    ]
    assert "La taza está sobre la mesa." in questions[-1].prompt
    key = _answer_key(engine, lesson.id)
    assert key["correctOptionIds"][questions[1].question_id] == "¿Dónde está la taza?"
    assert [item["targetIds"] for item in key["questionEvaluations"]] == [
        ["recognise-question", "name-object"],
        ["build-question", "name-object"],
        ["understand-location"],
    ]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public
    draft = _scalar(engine, select(sessions.c.analysis_draft).where(sessions.c.id == sid))
    assert draft["missionPlan"] == [
        {"missionId": "M02", "practiceLevel": "A1", "contentVersion": 1}
    ]


def test_valid_m02_model_lesson_uses_its_own_cache_identity(curated, monkeypatch):
    versions = []
    original = learning_service.run_cached

    def recording(*args, **kwargs):
        versions.append(kwargs["version"])
        return original(*args, **kwargs)

    monkeypatch.setattr(learning_service, "run_cached", recording)
    _repository_, _sid, detail = _lesson(curated, _relations_only, M02Model())
    assert detail.tasks[1].public_content.title == "Model lesson"
    assert [(v.prompt_version, v.schema_version) for v in versions] == [
        (f"{M02_PROMPT_VERSION}:M02-A1.v1", M02_SCHEMA_VERSION)
    ]


@pytest.mark.parametrize("scenario", ["correct", "partial", "incorrect"])
def test_m02_submissions_grade_each_question_once(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated, _relations_only)
    lesson = detail.tasks[1]
    questions = lesson.public_content.questions
    correct = _correct_answers(engine, lesson)
    wrong = {
        q.question_id: next(
            o.option_id for o in q.options if o.option_id != correct[q.question_id]
        ) if q.interaction_type == "multipleChoice" else "taza la está ¿Dónde ?"
        for q in questions
    }
    last = questions[-1].question_id
    answers = {
        "correct": correct, "partial": {**correct, last: wrong[last]}, "incorrect": wrong,
    }[scenario]
    first = _attempt(client, lesson, answers, key="m02-answer")
    assert first.status_code == 200, first.text
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    awarded = _scalar(engine, xp)
    repeat = _attempt(client, lesson, answers, key="m02-answer")
    assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
    assert _scalar(engine, xp) == awarded
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 1
    details = first.json()["attempt"]["evaluationDetails"]
    expected = {qid: answers[qid] == correct[qid] for qid in correct}
    assert details["questionResults"] == expected
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    assert outcomes[questions[1].question_id]["evidenceType"] == "construction"
    assert outcomes[questions[1].question_id]["assistance"] == ["wordBank"]
    if not expected[last]:
        assert outcomes[last]["mistakes"][0]["mistake"] == "wrongPosition"


def test_a_photo_fitting_both_plans_both_and_the_lesson_finishes_after_both(curated):
    engine, _owner, profile, client, *_ = curated
    repository, sid, detail = _lesson(curated)
    assert _planned(detail) == ["M01", "M02"]
    kinds = [task.kind for task in detail.tasks]
    assert kinds[:3] == ["vocabularyIntroduction", "grammarLesson", "grammarLesson"]
    assert "ispyRound" in kinds[3:]
    m01, m02 = detail.tasks[1], detail.tasks[2]
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
    assert "Ask where it is: Confirm where one object is" in tips
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
