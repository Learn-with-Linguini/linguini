"""M01 A1 mission lessons: eligibility, generation, grading, evidence and completion."""

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, TextModelResponse, services
from test_preloaded_templates_workflow import curated as curated

from app.ai.features.learning_tasks import service as learning_service
from app.ai.features.learning_tasks.mission import (
    M01_PROMPT_VERSION,
    M01_SCHEMA_VERSION,
    fallback_m01_lesson,
)
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.vocabulary import vocabulary_encounters
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import MissionPhotoNotReadyError
from app.schemas.sessions import ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest

M01 = ("M01", "A1", 1)


class MissionModel(SceneModel):
    """Answers the mission lesson request with valid content of its own."""

    def generate(self, request, **options):
        if request.json_schema_name != "mission_lesson_m01_v1":
            return super().generate(request, **options)
        self.requests.append(request.json_schema_name)
        result = fallback_m01_lesson(json.loads(request.user_content))
        body = result.model_copy(update={"title": "Model lesson"}).model_dump(
            mode="json", by_alias=True
        )
        return TextModelResponse(
            output_text=json.dumps(body), model_name="test-text-model",
            prompt_version=request.prompt_version, input_tokens=10, output_tokens=10,
        )


@pytest.fixture
def missions(monkeypatch):
    monkeypatch.setenv("MISSION_LESSONS_ENABLED", "true")


def _repository(curated, model):
    engine, owner, *_ = curated
    feature = services(model)
    return PostgresWorkflowRepository(
        engine, owner.id, translator=feature["translation"],
        learning_task_generator=feature["lessons"], ispy_clue_generator=feature["clues"],
    )


def _analyzed(curated, repository):
    _, _, profile, client, asset, _ = curated
    response = client.post("/api/v1/sessions", json={
        "languageProfileId": str(profile.id), "mediaAssetId": str(asset.id),
        "idempotencyKey": str(uuid4()),
    })
    assert response.status_code == 202, response.text
    sid = UUID(response.json()["session"]["id"])
    repository.analyze(sid, profile.id)
    return sid, repository.get(sid, profile.id)


def _review(detail):
    return ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in detail.scene_objects],
        object_attributes={
            obj.id: obj.attributes for obj in detail.scene_objects if obj.attributes
        },
        relations=detail.scene_object_relations,
    )


def _lesson(curated, model=None):
    profile = curated[2]
    repository = _repository(curated, model or SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    repository.review(sid, profile.id, _review(analyzed))
    return repository, sid, repository.get(sid, profile.id)


def _scalar(engine, query):
    with engine.connect() as connection:
        return connection.execute(query).scalar_one()


def _answer_key(engine, task_id):
    return _scalar(engine, select(session_tasks.c.answer_key).where(session_tasks.c.id == task_id))


def _attempt(client, task, answers, key="m01-answer", **extra):
    return client.post(f"/api/v1/tasks/{task.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": answers, "idempotencyKey": key, **extra,
    })


def test_suitable_photo_builds_one_mission_lesson_after_the_vocabulary(curated, missions):
    engine, _owner, _profile, client, *_ = curated
    model = SceneModel()
    _repository_, sid, detail = _lesson(curated, model)
    assert detail.session.status == "inProgress"
    assert [task.kind for task in detail.tasks] == ["vocabularyIntroduction", "grammarLesson"]
    assert all(task.public_content.mission_key == M01 for task in detail.tasks)
    lesson = detail.tasks[1]
    questions = lesson.public_content.questions
    assert 2 <= len(questions) <= 4
    assert [q.interaction_type for q in questions][-1] == "sentenceBuilding"
    assert {q.interaction_type for q in questions[:-1]} == {"multipleChoice"}
    # The scripted model has no mission answer, so the deterministic lesson is used.
    assert "mission_lesson_m01_v1" in model.requests
    assert lesson.public_content.title == "Name it and say its colour"
    key = _answer_key(engine, lesson.id)
    assert key["correctOptionIds"][questions[-1].question_id] == "La taza es roja."
    evaluations = key["questionEvaluations"]
    assert [item["questionId"] for item in evaluations] == [q.question_id for q in questions]
    assert evaluations[0]["targetIds"] == ["identify-object", "name-object"]
    assert evaluations[-1]["targetIds"] == ["name-object", "describe-colour"]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public


def test_valid_model_lesson_is_used_under_a_mission_cache_identity(
    curated, missions, monkeypatch,
):
    versions = []
    original = learning_service.run_cached

    def recording(*args, **kwargs):
        versions.append(kwargs["version"])
        return original(*args, **kwargs)

    monkeypatch.setattr(learning_service, "run_cached", recording)
    _repository_, _sid, detail = _lesson(curated, MissionModel())
    assert detail.tasks[1].public_content.title == "Model lesson"
    assert [(v.prompt_version, v.schema_version) for v in versions] == [
        (f"{M01_PROMPT_VERSION}:M01-A1.v1", M01_SCHEMA_VERSION)
    ]


def test_unsuitable_photo_can_be_reviewed_again_without_a_substitute_scene(curated, missions):
    profile = curated[2]
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    objects = analyzed.scene_objects
    status = analyzed.session.status
    coloured = next(obj for obj in objects if obj.attributes)
    for request, reason in [
        (ReviewPracticeRequest(accepted_object_ids=[obj.id for obj in objects]),
         "Confirm the colour of at least one object."),
        (ReviewPracticeRequest(
            accepted_object_ids=[coloured.id],
            object_attributes={coloured.id: coloured.attributes},
        ), "Confirm at least 2 different objects."),
    ]:
        with pytest.raises(MissionPhotoNotReadyError, match="not ready for this lesson") as error:
            repository.review(sid, profile.id, request)
        assert reason in str(error.value) and "choose another image" in str(error.value)
        detail = repository.get(sid, profile.id)
        assert detail.session.status == status and detail.tasks == []
    repository.review(sid, profile.id, _review(analyzed))
    assert repository.get(sid, profile.id).session.status == "inProgress"


@pytest.mark.parametrize(("enabled", "level"), [("false", "A1"), ("true", "A2")])
def test_flag_off_and_other_levels_keep_the_existing_lesson(
    curated, monkeypatch, enabled, level,
):
    engine, _owner, profile, *_ = curated
    monkeypatch.setenv("MISSION_LESSONS_ENABLED", enabled)
    with engine.begin() as connection:
        connection.execute(update(language_profiles).where(
            language_profiles.c.id == profile.id
        ).values(proficiency_level=level))
    _repository_, _sid, detail = _lesson(curated)
    assert "ispyRound" in {task.kind for task in detail.tasks}
    assert all(task.public_content.mission_key is None for task in detail.tasks)


@pytest.mark.parametrize("scenario", ["correct", "partial", "incorrect"])
def test_submissions_grade_each_question_and_word_once(curated, missions, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated)
    lesson = detail.tasks[1]
    questions = lesson.public_content.questions
    key = _answer_key(engine, lesson.id)
    correct = key["correctOptionIds"]
    wrong = {
        q.question_id: next(
            o.option_id for o in q.options if o.option_id != correct[q.question_id]
        ) if q.interaction_type == "multipleChoice" else "roja es taza La"
        for q in questions
    }
    last = questions[-1].question_id
    answers = {
        "correct": correct, "partial": {**correct, last: wrong[last]}, "incorrect": wrong,
    }[scenario]
    first = _attempt(client, lesson, answers)
    assert first.status_code == 200, first.text
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    awarded = _scalar(engine, xp)
    repeat = _attempt(client, lesson, answers)
    assert repeat.status_code == 200, repeat.text
    attempt = first.json()["attempt"]
    replayed = repeat.json()["attempt"]
    assert (replayed["id"], replayed["evaluationDetails"]) == (
        attempt["id"], attempt["evaluationDetails"]
    )
    assert _scalar(engine, xp) == awarded
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 1
    expected = {qid: answers[qid] == correct[qid] for qid in correct}
    details = attempt["evaluationDetails"]
    assert details["questionResults"] == expected
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    for question in questions:
        outcome = outcomes[question.question_id]
        assert outcome["outcome"] == (
            "correct" if expected[question.question_id] else "incorrect"
        )
        built = question.interaction_type == "sentenceBuilding"
        assert outcome["evidenceType"] == ("construction" if built else "recognition")
        assert outcome["assistance"] == (["wordBank"] if built else [])
        assert outcome["assistanceUsed"] is False
        assert bool(outcome["mistakes"]) is not expected[question.question_id]
    if not expected[last]:
        assert outcomes[last]["mistakes"][0]["correction"] == "La taza es roja."
    words = {}
    for item in key["questionEvaluations"]:
        for word in item["vocabularyItemIds"]:
            words[word] = words.get(word, True) and expected[item["questionId"]]
    with engine.connect() as connection:
        encounters = connection.execute(select(
            vocabulary_encounters.c.vocabulary_item_id, vocabulary_encounters.c.outcome
        ).where(vocabulary_encounters.c.session_task_id == lesson.id)).all()
    assert {str(word): outcome for word, outcome in encounters} == {
        word: "correct" if result else "incorrect" for word, result in words.items()
    }


def test_offered_support_is_recorded_and_the_lesson_finishes_without_ispy(curated, missions):
    engine, _owner, profile, client, *_ = curated
    repository, sid, detail = _lesson(curated)
    introduction, lesson = detail.tasks
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    first = lesson.public_content.questions[0].question_id
    refused = _attempt(client, lesson, correct, questionAssistance=[
        {"questionId": first, "supports": ["hint"]},
    ])
    assert refused.status_code == 409
    response = _attempt(client, lesson, correct, questionAssistance=[
        {"questionId": first, "supports": ["audio"]},
    ])
    assert response.status_code == 200, response.text
    outcome = response.json()["attempt"]["evaluationDetails"]["questionOutcomes"][0]
    assert outcome["assistance"] == ["audio"] and outcome["assistanceUsed"] is False
    payload = _scalar(engine, select(task_attempts.c.response_payload).where(
        task_attempts.c.session_task_id == lesson.id
    ))
    assert payload["question_assistance"] == [{"question_id": first, "supports": ["audio"]}]
    repository.task_action(introduction.id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted",
    )) == 1
