from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from test_missions import (
    HIDDEN_OBJECT,
    HIDDEN_WORD,
    MISSION,
    answer_key,
    evaluations,
    lesson_content,
)
from test_postgres_sessions import analyze, create_run
from test_postgres_sessions import database as database

from app.repositories.postgres.learner_history import snapshot_learner_history
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import PostgresTaskRepository, session_tasks, task_attempts
from app.repositories.postgres.vocabulary import vocabulary_items
from app.schemas.tasks import SessionTask
from app.schemas.vocabulary import VocabularyItem

ANSWERS = {"colour": "rojo", "build": "La taza es roja.", "extra": "taza"}


@pytest.fixture
def lessons(database):
    engine, owner, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    analyze(client, sid)
    repository = PostgresTaskRepository(engine)
    with engine.begin() as connection:
        connection.execute(pg_insert(vocabulary_items).values(**VocabularyItem(
            id=HIDDEN_WORD, language_code="es", lemma="taza-oculta", display_text="taza",
            part_of_speech="noun",
        ).model_dump(by_alias=False)).on_conflict_do_nothing())

    def lesson(order_index, content, key):
        task = SessionTask(
            session_id=sid, phase="learning", kind="grammarLesson", order_index=order_index,
            public_content=content, answer_key=key,
        )
        return repository.create_task(task, owner.id)

    mission = lesson(100, lesson_content(**MISSION), answer_key(questionEvaluations=evaluations()))
    legacy = lesson(101, lesson_content(), answer_key())
    yield engine, owner, profile, client, repository, mission, legacy
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.user_id == owner.id))


def stored(engine, table, column, task_id):
    key = table.c.id if table is session_tasks else table.c.session_task_id
    with engine.connect() as connection:
        return connection.execute(select(column).where(key == task_id)).scalar_one()


def test_mission_task_round_trips_and_stays_private(lessons):
    engine, owner, _profile, client, repository, mission, legacy = lessons
    assert repository.get(mission.id, owner.id) == mission
    assert repository.get(legacy.id, owner.id) == legacy
    content = stored(engine, session_tasks, session_tasks.c.public_content, mission.id)
    assert {key: content[key] for key in MISSION} == MISSION
    key = stored(engine, session_tasks, session_tasks.c.answer_key, mission.id)
    assert key["questionEvaluations"][0]["vocabularyItemIds"] == [str(HIDDEN_WORD)]
    legacy_content = stored(engine, session_tasks, session_tasks.c.public_content, legacy.id)
    assert not set(MISSION) & set(legacy_content)
    assert "questionEvaluations" not in stored(
        engine, session_tasks, session_tasks.c.answer_key, legacy.id
    )
    for endpoint in [f"/api/v1/tasks/{mission.id}", f"/api/v1/sessions/{mission.session_id}"]:
        response = client.get(endpoint)
        assert response.status_code == 200, response.text
        for private in ["answerKey", "questionEvaluations", "correctOptionIds", "wrongGender",
                        str(HIDDEN_WORD), str(HIDDEN_OBJECT)]:
            assert private not in response.text
    public = client.get(f"/api/v1/tasks/{mission.id}").json()["publicContent"]
    assert {key: public[key] for key in MISSION} == MISSION
    assert not set(MISSION) & set(client.get(f"/api/v1/tasks/{legacy.id}").json()["publicContent"])


def test_mission_attempt_adds_outcomes_and_keeps_legacy_contract(lessons):
    engine, owner, profile, client, _repository, mission, legacy = lessons
    results = {}
    for task, extra in [
        (mission, {"questionAssistance": [{"questionId": "extra", "supports": ["audio"]}]}),
        (legacy, {}),
    ]:
        response = client.post(f"/api/v1/tasks/{task.id}/attempts", json={
            "inputMode": "vocabularyReview", "answers": ANSWERS, **extra,
        })
        assert response.status_code == 200, response.text
        results[task.id] = response.json()["attempt"]
    graded, plain = results[mission.id], results[legacy.id]
    assert set(plain["evaluationDetails"]) == {"questionResults", "correctAnswers"}
    assert {key: graded["evaluationDetails"][key] for key in plain["evaluationDetails"]} == (
        plain["evaluationDetails"]
    )
    for field in ["isCorrect", "score", "feedback"]:
        assert graded[field] == plain[field]
    outcomes = {item["questionId"]: item for item in graded["evaluationDetails"][
        "questionOutcomes"
    ]}
    assert [outcomes[key]["outcome"] for key in ANSWERS] == ["incorrect", "correct", "unassessed"]
    assert outcomes["colour"]["mistakes"][0]["mistake"] == "wrongGender"
    assert outcomes["extra"]["assistance"] == ["audio"]
    assert outcomes["extra"]["assistanceUsed"] is False
    payload = stored(engine, task_attempts, task_attempts.c.response_payload, mission.id)
    assert payload["question_assistance"] == [{"question_id": "extra", "supports": ["audio"]}]
    assert "question_assistance" not in stored(
        engine, task_attempts, task_attempts.c.response_payload, legacy.id
    )
    details = stored(engine, task_attempts, task_attempts.c.evaluation_details, mission.id)
    assert details == graded["evaluationDetails"]
    assert "answerKey" not in str(graded) and str(HIDDEN_OBJECT) not in str(graded)
    with engine.connect() as connection:
        history = snapshot_learner_history(
            connection, owner.id, profile.model_dump(by_alias=False), uuid4(), []
        )
    # Learner history reads questionResults only, so both lessons count identically.
    assert history["grammar"]["genderNumberAgreement"] == {
        "correctCount": 4, "incorrectCount": 2, "lastOutcome": "incorrect",
    }
    response = client.post(f"/api/v1/tasks/{legacy.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": ANSWERS,
        "questionAssistance": [{"questionId": "missing", "supports": ["hint"]}],
    })
    assert response.status_code == 409


def test_legacy_rows_without_mission_metadata_still_load(lessons):
    engine, owner, _profile, client, repository, _mission, legacy = lessons
    detail = client.get(f"/api/v1/sessions/{legacy.session_id}")
    assert detail.status_code == 200, detail.text
    assert all(
        not set(MISSION) & set(task["publicContent"]) for task in detail.json()["tasks"]
        if UUID(task["id"]) != _mission.id
    )
    assert repository.get(legacy.id, owner.id).public_content.mission_key is None
    assert repository.get(uuid4(), owner.id) is None
