from uuid import uuid4, uuid5

import pytest
from sqlalchemy import func, select, update
from test_mission_m01_workflow import _analyzed, _scalar
from test_mission_m02_workflow import _without_clue_model
from test_missions_a2_workflow import _answer_key
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_objects
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.vocabulary import user_vocabulary_progress, vocabulary_encounters
from app.repositories.postgres.workflow import _m06_feedback
from app.repositories.postgres.xp import xp_events
from app.schemas.sessions import AddedPracticeObject, ReviewPracticeRequest
from app.services.mission_eligibility import lesson_missions


def _m06_for_language(curated, language="de", level="A2"):
    engine, _owner, profile, client, *_ = curated
    with engine.begin() as connection:
        connection.execute(
            update(language_profiles)
            .where(language_profiles.c.id == profile.id)
            .values(target_language_code=language, proficiency_level=level)
        )
    repository = _without_clue_model(curated, SceneModel())
    session_id, analyzed = _analyzed(curated, repository)
    cup = next(obj for obj in analyzed.scene_objects if obj.label == "cup")
    added_book = AddedPracticeObject(id=uuid4(), label="book", x=0.75, y=0.5)
    repository.review(
        session_id,
        profile.id,
        ReviewPracticeRequest(
            accepted_object_ids=[cup.id],
            added_objects=[added_book],
            object_attributes={cup.id: {"color": "red"}},
            relations=[],
            object_counts={cup.id: 2},
        ),
    )
    return engine, client, repository, session_id, repository.get(session_id, profile.id)


def _mission_snapshot(engine, detail):
    return [
        (
            str(task.id),
            task.public_content.model_dump(mode="json", by_alias=True),
            _answer_key(engine, task.id)["missionState"],
        )
        for task in detail.tasks
        if task.public_content.mission_id == "M06"
    ]


def _submit_m06_task(client, engine, task, *, key):
    correct = _answer_key(engine, task.id)["correctOptionIds"]
    for question in task.public_content.questions:
        checked = client.post(
            f"/api/v1/tasks/{task.id}/check-lesson-answer",
            json={"questionId": question.question_id, "answer": correct[question.question_id]},
        )
        assert checked.status_code == 200, checked.text
    request = {"inputMode": "vocabularyReview", "answers": correct, "idempotencyKey": key}
    submitted = client.post(f"/api/v1/tasks/{task.id}/attempts", json=request)
    assert submitted.status_code == 200, submitted.text
    return request, submitted


def test_m06_builds_two_stable_tasks_and_records_scenario_assistance(curated):
    engine, client, repository, session_id, detail = _m06_for_language(curated)
    tasks = [task for task in detail.tasks if task.public_content.mission_id == "M06"]
    assert len(tasks) == 2
    assert [task.id for task in tasks] == [
        uuid5(session_id, "mission:M06-A2.v1:lesson"),
        uuid5(session_id, "mission:M06-A2.v1:lesson-2"),
    ]
    assert [task.order_index for task in tasks] == list(
        range(tasks[0].order_index, tasks[0].order_index + 2)
    )
    assert all(task.public_content.check_each_question for task in tasks)
    # A pack lesson's sentences are about its own item, so it offers no other item.
    assert tasks[0].public_content.scenario.alternatives == []
    before = _mission_snapshot(engine, detail)
    first_get = client.get(f"/api/v1/sessions/{session_id}").json()
    second_get = client.get(f"/api/v1/sessions/{session_id}").json()
    assert [
        task["publicContent"] for task in first_get["tasks"]
        if task["publicContent"].get("missionId") == "M06"
    ] == [
        task["publicContent"] for task in second_get["tasks"]
        if task["publicContent"].get("missionId") == "M06"
    ]
    regenerated_claim = repository._claim_generation(session_id, detail.session.language_profile_id)
    repository._generate_tasks(regenerated_claim)
    assert _mission_snapshot(
        engine, repository.get(session_id, detail.session.language_profile_id)
    ) == before
    with engine.connect() as connection:
        initial_attributes = (
            connection.execute(
                select(scene_objects.c.attributes).where(scene_objects.c.session_id == session_id)
            )
            .scalars()
            .all()
        )
    refreshed = repository.get(session_id, detail.session.language_profile_id)
    assert [task.public_content.model_dump() for task in tasks] == [
        task.public_content.model_dump()
        for task in refreshed.tasks
        if task.public_content.mission_id == "M06"
    ]
    other = next(obj for obj in detail.scene_objects
                 if str(obj.id) != str(tasks[0].public_content.scenario.scene_object_id))
    refused = client.post(
        f"/api/v1/tasks/{tasks[0].id}/mission-scenario",
        json={"action": "choose", "sceneObjectId": str(other.id)},
    )
    assert refused.status_code == 409, refused.text

    accepted = client.post(
        f"/api/v1/tasks/{tasks[0].id}/mission-scenario", json={"action": "accept"}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted"] is True
    key = _answer_key(engine, tasks[0].id)
    correct = key["correctOptionIds"]["m06-q1"]
    wrong = "wrong-quantity"
    out_of_order = client.post(
        f"/api/v1/tasks/{tasks[0].id}/lesson-assistance",
        json={
            "questionId": "m06-q1",
            "step": "visualDetail",
        },
    )
    assert out_of_order.status_code == 409
    replay = client.post(
        f"/api/v1/tasks/{tasks[0].id}/lesson-assistance",
        json={
            "questionId": "m06-q1",
            "step": "replayAudio",
        },
    )
    assert replay.status_code == 200, replay.text
    detail_hint = client.post(
        f"/api/v1/tasks/{tasks[0].id}/lesson-assistance",
        json={"questionId": "m06-q1", "step": "visualDetail"},
    )
    assert detail_hint.status_code == 200, detail_hint.text
    assistance_state = client.get(f"/api/v1/tasks/{tasks[0].id}/lesson-checks")
    assert assistance_state.status_code == 200
    assert assistance_state.json()["assistanceSteps"]["m06-q1"] == [
        "replayAudio",
        "visualDetail",
    ]
    checked = client.post(
        f"/api/v1/tasks/{tasks[0].id}/check-lesson-answer",
        json={
            "questionId": "m06-q1",
            "answer": wrong,
        },
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["attemptsLeft"] == 2
    assert checked.json()["correctAnswer"] is None
    assert checked.json()["wrongField"] == "quantity"
    expected_quantity = key["missionState"]["transaction"]["quantity"]
    quantity_word = {1: "one", 2: "two", 3: "three"}[expected_quantity]
    assert checked.json()["feedback"] == f"Check the quantity — the order was for {quantity_word}."
    correct_check = client.post(
        f"/api/v1/tasks/{tasks[0].id}/check-lesson-answer",
        json={
            "questionId": "m06-q1",
            "answer": correct,
        },
    )
    assert correct_check.status_code == 200, correct_check.text
    assert correct_check.json()["assistanceStepsUsed"] == ["replayAudio", "visualDetail"]
    restored = client.get(f"/api/v1/tasks/{tasks[0].id}/lesson-checks")
    assert restored.status_code == 200
    assert restored.json()["checks"][0]["answer"] == correct
    assert restored.json()["assistanceSteps"]["m06-q1"] == ["replayAudio", "visualDetail"]
    for question in tasks[0].public_content.questions[1:]:
        qcheck = client.post(
            f"/api/v1/tasks/{tasks[0].id}/check-lesson-answer",
            json={
                "questionId": question.question_id,
                "answer": key["correctOptionIds"][question.question_id],
            },
        )
        assert qcheck.status_code == 200, qcheck.text
    request = {
        "inputMode": "vocabularyReview",
        "answers": key["correctOptionIds"],
        "idempotencyKey": "m06-assisted-submit",
    }
    submitted = client.post(f"/api/v1/tasks/{tasks[0].id}/attempts", json=request)
    assert submitted.status_code == 200, submitted.text
    q1_outcome = next(
        item for item in submitted.json()["attempt"]["evaluationDetails"]["questionOutcomes"]
        if item["questionId"] == "m06-q1"
    )
    assert q1_outcome["assistanceUsed"] is True
    assert q1_outcome["assistance"] == ["audio", "hint"]
    with engine.connect() as connection:
        answer_key = connection.execute(
            select(session_tasks.c.answer_key).where(session_tasks.c.id == tasks[0].id)
        ).scalar_one()
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == session_id)
        ).scalar_one()
        final_attributes = (
            connection.execute(
                select(scene_objects.c.attributes).where(scene_objects.c.session_id == session_id)
            )
            .scalars()
            .all()
        )
    # The refused switch left the lesson's own item in place.
    item_label = tasks[0].public_content.scenario.item_label
    assert answer_key["missionState"]["transaction"]["itemLabel"] == item_label
    m06_plan = next(item for item in draft["missionPlan"] if item["missionId"] == "M06")
    assert m06_plan["transaction"]["itemLabel"] == item_label
    assert final_attributes == initial_attributes


def test_m06_skips_both_mission_tasks(curated):
    _engine, client, _repository, session_id, detail = _m06_for_language(curated)
    tasks = [task for task in detail.tasks if task.public_content.mission_id == "M06"]
    for task in tasks:
        response = client.post(f"/api/v1/tasks/{task.id}/skip", json={})
        assert response.status_code == 200, response.text
    refreshed = client.get(f"/api/v1/sessions/{session_id}").json()
    m06_tasks = [
        task for task in refreshed["tasks"] if task["publicContent"].get("missionId") == "M06"
    ]
    assert len(m06_tasks) == 2
    assert [task["status"] for task in m06_tasks] == ["skipped", "skipped"]


def test_m06_feedback_names_each_transaction_detail_in_english():
    transaction = {
        "quantity": 2,
        "requestDetails": {"size": "small"},
        "itemLabel": "coffee",
        "followUp": {"type": "temperature", "value": "cold"},
        "serviceSetting": "takeAway",
        "mismatch": {
            "flag": False,
            "field": None,
            "servedValue": None,
            "correctedValue": None,
        },
    }
    expected = {
        "quantity": "Check the quantity — the order was for two.",
        "size": "Check the size — the order was small.",
        "item": "Check the item — the order was for coffee.",
        "temperature": "Check hot or cold — you wanted it cold.",
        "serviceSetting": "Check eat in or take away — you wanted it to take away.",
        "colour": "Check the colour — you wanted blue.",
        "request": "Use the polite request phrase.",
    }
    for field, feedback in expected.items():
        transaction["followUp"] = {
            "type": field if field in {"temperature", "colour"} else "temperature",
            "value": "blue" if field == "colour" else "cold",
        }
        assert _m06_feedback(transaction, "m06-q1", field)[1] == feedback
    transaction["mismatch"] = {"flag": True, "field": "quantity"}
    assert _m06_feedback(transaction, "m06-q6", "quantity") == (
        "quantity",
        "The server got the quantity wrong — correct it.",
    )
    transaction["mismatch"] = {"flag": False}
    assert _m06_feedback(transaction, "m06-q6", "quantity") == (
        "confirmOrRepair",
        "The server repeated your order correctly — confirm it.",
    )


@pytest.mark.parametrize("language,level,expected", [
    ("de", "A1", ["M01", "M02", "M03", "M04", "M05"]),
    ("es", "A1", ["M01", "M02", "M03", "M04", "M05"]),
    ("es", "A0", ["M01", "M02", "M03", "M04", "M05", "M13"]),
])
def test_existing_a1_and_a0_profiles_keep_their_mission_plans(
    curated, language, level, expected
):
    _engine, _client, _repository, _session_id, detail = _m06_for_language(
        curated, language=language, level=level
    )
    assert [
        mission.mission_id for mission in lesson_missions(
            "lesson", {"proficiency_level": level, "target_language_code": language}
        )
    ] == expected
    plan = detail.session.analysis_draft.get("missionPlan", [])
    assert "M06" not in {item["missionId"] for item in plan}
    assert {item["missionId"] for item in plan} <= set(expected)


def test_m06_submissions_are_idempotent_and_session_finishes_after_learning(curated):
    engine, client, _repository, session_id, detail = _m06_for_language(curated)
    tasks = [task for task in detail.tasks if task.public_content.mission_id == "M06"]
    for task in detail.tasks:
        if task.public_content.mission_id != "M06":
            skipped = client.post(f"/api/v1/tasks/{task.id}/skip", json={})
            assert skipped.status_code == 200, skipped.text
    pending = []
    for index, task in enumerate(tasks):
        request, submitted = _submit_m06_task(client, engine, task, key=f"m06-final-{index}")
        pending.append((task, request, submitted))

    counts_after_first_submit = (
        _scalar(
            engine,
            select(func.count()).select_from(xp_events).where(
                xp_events.c.session_id == session_id
            ),
        ),
        _scalar(
            engine,
            select(func.count()).select_from(vocabulary_encounters).where(
                vocabulary_encounters.c.session_id == session_id
            ),
        ),
        _scalar(
            engine,
            select(func.count()).select_from(user_vocabulary_progress).where(
                user_vocabulary_progress.c.user_id == detail.session.user_id
            ),
        ),
    )
    for task, request, submitted in pending:
        repeated = client.post(f"/api/v1/tasks/{task.id}/attempts", json=request)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["attempt"]["id"] == submitted.json()["attempt"]["id"]

    counts_after_replay = (
        _scalar(
            engine,
            select(func.count()).select_from(xp_events).where(
                xp_events.c.session_id == session_id
            ),
        ),
        _scalar(
            engine,
            select(func.count()).select_from(vocabulary_encounters).where(
                vocabulary_encounters.c.session_id == session_id
            ),
        ),
        _scalar(
            engine,
            select(func.count()).select_from(user_vocabulary_progress).where(
                user_vocabulary_progress.c.user_id == detail.session.user_id
            ),
        ),
    )
    assert counts_after_replay == counts_after_first_submit
    assert _scalar(
        engine,
        select(func.count()).select_from(task_attempts).where(
            task_attempts.c.session_task_id.in_([task.id for task in tasks])
        ),
    ) == 2
    assert client.post(f"/api/v1/sessions/{session_id}/complete").status_code == 200
    completed = client.get(f"/api/v1/sessions/{session_id}").json()
    assert completed["session"]["status"] == "completed"
    assert client.get(f"/api/v1/sessions/{session_id}/summary").status_code == 200
    assert _scalar(
        engine,
        select(func.count()).select_from(xp_events).where(
            xp_events.c.session_id == session_id, xp_events.c.event_type == "sessionCompleted"
        ),
    ) == 1
