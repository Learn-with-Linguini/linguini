"""M01 A1 mission lessons: eligibility, generation, grading, evidence and completion."""

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, TextModelResponse, services
from test_preloaded_templates_workflow import curated as curated

from app.ai.features.learning_tasks.mission_m01 import (
    fallback_m01_lesson,
)
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import user_vocabulary_progress, vocabulary_encounters
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.sessions import ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest
from app.services import mission_eligibility, mission_lessons_m01

M01 = ("M01", "A1", 1)


@pytest.fixture(autouse=True)
def m01_only(monkeypatch):
    """Keep these photos to the M01 lesson; M02 and M03 have their own workflow tests."""
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (M01,))


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


def _colours(detail):
    """The analysed colours, with the uncoloured objects confirmed as white."""
    return {obj.id: obj.attributes or {"color": "white"} for obj in detail.scene_objects}


def _review(detail):
    return ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in detail.scene_objects],
        object_attributes=_colours(detail),
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


def test_suitable_photo_builds_one_mission_lesson_after_the_vocabulary(curated):
    engine, _owner, _profile, client, *_ = curated
    model = SceneModel()
    _repository_, sid, detail = _lesson(curated, model)
    assert detail.session.status == "inProgress" and detail.mission_guidance == []
    kinds = [task.kind for task in detail.tasks]
    assert kinds[:2] == ["vocabularyIntroduction", "grammarLesson"]
    assert "ispyRound" in kinds[2:] and set(kinds[2:]) <= {"ispyRound", "reflection"}
    assert detail.tasks[0].public_content.mission_key is None
    assert detail.tasks[1].public_content.mission_key == M01
    assert all(task.public_content.mission_key is None for task in detail.tasks[2:])
    lesson = detail.tasks[1]
    questions = lesson.public_content.questions
    assert [q.interaction_type for q in questions] == [
        "multipleChoice", "multipleChoice", "multipleChoice", "sentenceBuilding",
    ]
    assert {questions[0].prompt, questions[1].prompt} <= {"¿Es una taza?", "¿Es una mesa?"}
    assert all(o.label.startswith(("Sí, es ", "No, es ")) for q in questions[:2] for o in q.options)
    assert [q.prompt for q in questions[2:]] == ["¿De qué color es?", "Describe este objeto."]
    assert [q.section for q in questions] == [
        "Task 1 · Identify objects in your photo", "Task 1 · Identify objects in your photo",
        "Task 2 · Describe them", "Task 2 · Describe them",
    ]
    objects = [q.scene_object_id for q in questions]
    assert objects[0] == objects[2] != objects[1] == objects[3]
    # Identification never shows the English name before the answer.
    labels = [q.object_label for q in questions]
    assert labels[:2] == [None, None] and labels[2] != labels[3]
    assert [q.keep_option_order for q in questions] == [True, True, True, None]
    # M01 is built from the confirmed facts without a model call.
    assert not any(name.startswith("mission_lesson_m01") for name in model.requests)
    assert lesson.public_content.title == "Name it and describe it"
    key = _answer_key(engine, lesson.id)
    described = key["correctOptionIds"]["describe-object"]
    assert described in {"Es una taza roja.", "Es una mesa blanca."}
    assert key["statementCorrect"].keys() == {"confirm-first", "confirm-second"}
    assert "." not in questions[3].token_bank
    public = lesson.public_content.model_dump_json()
    assert described not in public and "statementCorrect" not in public
    evaluations = key["questionEvaluations"]
    assert [item["questionId"] for item in evaluations] == [q.question_id for q in questions]
    assert evaluations[0]["targetIds"] == ["identify-object", "name-object"]
    assert evaluations[3]["targetIds"] == ["name-object", "describe-colour"]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public


def test_less_familiar_pairs_come_first_and_resume_keeps_them(curated):
    engine, owner, profile, *_ = curated
    earlier, first_sid, first = _lesson(curated)
    earlier.finish(first_sid, profile.id, abandon=True)
    named = {obj.id: obj for obj in first.scene_objects}
    shown = [named[q.scene_object_id] for q in first.tasks[1].public_content.questions[:2]]
    order = [obj.label for obj in shown]
    familiar = shown[0].vocabulary_item_id
    with engine.begin() as connection:
        connection.execute(update(user_vocabulary_progress).where(
            user_vocabulary_progress.c.user_id == owner.id,
            user_vocabulary_progress.c.vocabulary_item_id == familiar,
        ).values(mastery_score=1))
    repository, sid, detail = _lesson(curated)
    questions = detail.tasks[1].public_content.questions
    named = {obj.id: obj.label for obj in detail.scene_objects}
    assert [named[q.scene_object_id] for q in questions[:2]] == list(reversed(order))
    resumed = repository.get(sid, profile.id).tasks[1]
    assert resumed.public_content == detail.tasks[1].public_content


def test_a_photo_no_mission_fits_gets_the_regular_lesson_with_tips(curated):
    _engine, _owner, profile, client, *_ = curated
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    coloured = next(obj for obj in analyzed.scene_objects if obj.attributes)
    repository.review(sid, profile.id, ReviewPracticeRequest(
        accepted_object_ids=[coloured.id],
        object_attributes={coloured.id: coloured.attributes},
    ))
    detail = repository.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    assert detail.session.analysis_draft["missionPlan"] == []
    assert all(task.public_content.mission_key is None for task in detail.tasks)
    tips = " ".join(detail.mission_guidance)
    assert "Identify and describe an object: Confirm at least 2 different objects." in tips
    response = client.get(f"/api/v1/sessions/{sid}").json()
    assert response["missionGuidance"] == detail.mission_guidance


def test_a_session_confirmed_without_a_mission_plan_is_planned_at_generation(curated):
    engine, _owner, profile, *_ = curated
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    repository._review(sid, profile.id, _review(analyzed))
    with engine.begin() as connection:
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == sid)
        ).scalar_one()
        draft.pop("missionPlan")
        connection.execute(
            update(sessions).where(sessions.c.id == sid).values(analysis_draft=draft)
        )

    claim = repository._claim_generation(sid, profile.id)
    assert [mission.mission_id for mission in claim.missions] == ["M01"]
    repository._generate_tasks(claim)

    detail = repository.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    assert detail.tasks[1].public_content.mission_key == M01
    assert any(
        entry["missionId"] == "M01"
        for entry in detail.session.analysis_draft["missionPlan"]
    )


def test_an_empty_saved_mission_plan_stays_unplanned(curated):
    engine, _owner, profile, *_ = curated
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    repository._review(sid, profile.id, _review(analyzed))
    with engine.begin() as connection:
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == sid)
        ).scalar_one()
        draft["missionPlan"] = []
        connection.execute(
            update(sessions).where(sessions.c.id == sid).values(analysis_draft=draft)
        )

    claim = repository._claim_generation(sid, profile.id)
    assert claim.missions == ()



def test_a_colour_without_a_reviewed_form_skips_m01_for_the_regular_lesson(
    curated, monkeypatch,
):
    monkeypatch.setattr(mission_lessons_m01, "agreed_attribute", lambda *_: None)
    model = SceneModel()
    _repository_, _sid, detail = _lesson(curated, model)
    assert detail.session.status == "inProgress"
    assert detail.session.analysis_draft["skippedMissions"] == [
        {"missionId": "M01", "reason": "noReviewedContent"}
    ]
    assert "learning_tasks_v2" in model.requests
    assert any(
        task.kind == "grammarLesson" and task.public_content.mission_key is None
        for task in detail.tasks
    )
    assert "ispyRound" in {task.kind for task in detail.tasks}
    assert all(task.public_content.mission_key is None for task in detail.tasks)

@pytest.mark.parametrize("level", ["A0", "A2"])
def test_other_levels_keep_the_existing_lesson(curated, level):
    engine, owner, profile, *_ = curated
    with engine.begin() as connection:
        connection.execute(update(language_profiles).where(
            language_profiles.c.id == profile.id
        ).values(proficiency_level=level))
        connection.execute(update(users).where(
            users.c.id == owner.id
        ).values(onboarding_completed=True))
    _repository_, _sid, detail = _lesson(curated)
    assert "ispyRound" in {task.kind for task in detail.tasks}
    assert all(task.public_content.mission_key is None for task in detail.tasks)
    assert detail.mission_guidance == []


@pytest.mark.parametrize("scenario", ["correct", "partial", "incorrect"])
def test_submissions_grade_each_question_and_word_once(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated)
    lesson = detail.tasks[1]
    questions = lesson.public_content.questions
    key = _answer_key(engine, lesson.id)
    correct = key["correctOptionIds"]
    wrong = {
        q.question_id: next(
            o.option_id for o in q.options if o.option_id != correct[q.question_id]
        ) if q.interaction_type == "multipleChoice" else " ".join(reversed(q.token_bank))
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
        assert outcomes[last]["mistakes"][0]["correction"] == correct[last]
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


def test_offered_support_is_recorded_and_the_lesson_finishes_after_bonus_ispy(curated):
    engine, _owner, profile, client, *_ = curated
    repository, sid, detail = _lesson(curated)
    introduction, lesson, *bonus = detail.tasks
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
    with pytest.raises(PracticeConflictError):
        repository.finish(sid, profile.id)
    for task in bonus:
        repository.task_action(task.id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted",
    )) == 1


def test_latest_attempt_restores_answers_and_keeps_the_saved_option_order(curated):
    engine, _owner, profile, client, *_ = curated
    repository, sid, detail = _lesson(curated)
    lesson = detail.tasks[1]
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    assert _attempt(client, lesson, correct).status_code == 200
    restored = client.get(f"/api/v1/tasks/{lesson.id}/latest-attempt")
    assert restored.status_code == 200, restored.text
    saved = restored.json()["attempt"]
    assert saved["answers"] == correct
    assert saved["reviewDetails"]["questionResults"] == {qid: True for qid in correct}
    resumed = repository.get(sid, profile.id).tasks[1].public_content.questions
    assert [[o.option_id for o in q.options] for q in resumed] == [
        [o.option_id for o in q.options] for q in lesson.public_content.questions
    ]
