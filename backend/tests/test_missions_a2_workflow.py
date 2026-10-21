"""A2 mission generation and sequential answer checks in a curated scene."""

from uuid import uuid4

from sqlalchemy import func, select, update
from test_mission_m01_workflow import _analyzed, _scalar
from test_mission_m02_workflow import _without_clue_model
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_objects
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import (
    user_vocabulary_progress,
    vocabulary_encounters,
    vocabulary_items,
)
from app.repositories.postgres.xp import xp_events
from app.schemas.sessions import AddedPracticeObject, ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest


def _lesson(curated):
    engine, _owner, profile, client, *_ = curated
    with engine.begin() as connection:
        connection.execute(update(language_profiles).where(
            language_profiles.c.id == profile.id
        ).values(proficiency_level="A2"))
    model = SceneModel()
    repository = _without_clue_model(curated, model)
    sid, analyzed = _analyzed(curated, repository)
    cup = next(obj for obj in analyzed.scene_objects if obj.label == "cup")
    table = next(obj for obj in analyzed.scene_objects if obj.label == "table")
    added = AddedPracticeObject(id=uuid4(), label="chair", x=0.75, y=0.5)
    request = ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in analyzed.scene_objects],
        added_objects=[added],
        object_attributes={
            cup.id: {"color": "red"},
            table.id: {"color": "red"},
        },
        relations=analyzed.scene_object_relations,
        object_counts={cup.id: 2, table.id: 3},
    )
    repository.review(sid, profile.id, request)
    return engine, client, repository, sid, repository.get(sid, profile.id), cup, table


def _answer_key(engine, task_id):
    with engine.connect() as connection:
        return connection.execute(
            select(session_tasks.c.answer_key).where(session_tasks.c.id == task_id)
        ).scalar_one()


def _mission_snapshot(engine, detail):
    rows = []
    for task in detail.tasks:
        if not task.public_content.mission_id:
            continue
        rows.append(
            (
                str(task.id),
                task.public_content.model_dump(mode="json", by_alias=True),
                _answer_key(engine, task.id)["missionState"],
            )
        )
    return rows


def test_curated_photo_plans_four_a2_missions_and_locks_checks(curated):
    engine, client, repository, sid, detail, _cup, _table = _lesson(curated)
    lessons = [task for task in detail.tasks if task.public_content.mission_id]
    assert [task.public_content.mission_id for task in lessons] == [
        "M01", "M02", "M03", "M04",
    ]
    assert all(task.public_content.check_each_question for task in lessons)
    assert all(len(task.public_content.questions) == 5 for task in lessons)

    lesson = lessons[0]
    questions = lesson.public_content.questions
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    assert set(correct) == {question.question_id for question in questions}
    out_of_order = client.post(
        f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
        json={"questionId": questions[1].question_id, "answer": correct[questions[1].question_id]},
    )
    assert out_of_order.status_code == 409

    xp_before = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid
    ))
    for question in questions:
        response = client.post(
            f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
            json={"questionId": question.question_id, "answer": correct[question.question_id]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["isCorrect"] is True
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 0
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid
    )) == xp_before

    repeat = client.post(
        f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
        json={"questionId": questions[0].question_id, "answer": "changed-after-check"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["answer"] == correct[questions[0].question_id]
    restored = client.get(f"/api/v1/tasks/{lesson.id}/lesson-checks")
    assert restored.status_code == 200
    assert [check["questionId"] for check in restored.json()["checks"]] == [
        question.question_id for question in questions
    ]

    mismatched = dict(correct)
    first = questions[0]
    mismatched[first.question_id] = next(
        option.option_id for option in first.options
        if option.option_id != correct[first.question_id]
    )
    rejected = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": mismatched,
        "idempotencyKey": "a2-mismatch",
    })
    assert rejected.status_code == 409

    submitted = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": correct,
        "idempotencyKey": "a2-locked-answers",
    })
    assert submitted.status_code == 200, submitted.text
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 1
    evidence_count = _scalar(engine, select(func.count()).select_from(
        vocabulary_encounters
    ).where(vocabulary_encounters.c.session_id == sid))
    xp_count = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid
    ))
    repeated = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": correct,
        "idempotencyKey": "a2-locked-answers",
    })
    assert repeated.status_code == 200, repeated.text
    rekeyed = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": correct,
        "idempotencyKey": "a2-locked-answers-new-key",
    })
    assert rekeyed.status_code in {200, 409}, rekeyed.text
    assert _scalar(engine, select(func.count()).select_from(
        vocabulary_encounters
    ).where(vocabulary_encounters.c.session_id == sid)) == evidence_count
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid
    )) == xp_count
    for task in repository.get(sid, detail.session.language_profile_id).tasks:
        if task.status not in {"completed", "skipped"}:
            repository.task_action(task.id, "skip", SkipTaskRequest())
    repository.finish(sid, detail.session.language_profile_id)
    completed_xp = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted",
    ))
    assert completed_xp == 1
    repository.finish(sid, detail.session.language_profile_id)
    assert _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted",
    )) == completed_xp


def test_a2_generation_retry_preserves_ids_content_and_mission_state(curated):
    engine, _client, repository, sid, detail, *_ = _lesson(curated)
    before = _mission_snapshot(engine, detail)
    claim = repository._claim_generation(sid, detail.session.language_profile_id)
    repository._generate_tasks(claim)
    regenerated = repository.get(sid, detail.session.language_profile_id)
    after_first_retry = _mission_snapshot(engine, regenerated)
    claim = repository._claim_generation(sid, detail.session.language_profile_id)
    repository._generate_tasks(claim)
    regenerated_again = repository.get(sid, detail.session.language_profile_id)
    after_second_retry = _mission_snapshot(engine, regenerated_again)
    assert before == after_first_retry == after_second_retry


def test_m03_wrong_q4_keeps_the_false_count_in_fictional_mission_state_only(curated):
    engine, client, _repository, sid, detail, *_ = _lesson(curated)
    lesson = next(task for task in detail.tasks if task.public_content.mission_id == "M03")
    key = _answer_key(engine, lesson.id)
    false_count = next(
        fact for fact in key["missionState"]["approvedFacts"]["approvedRoleplayFacts"]
        if fact["kind"] == "falseCount"
    )
    questions = lesson.public_content.questions
    answers = dict(key["correctOptionIds"])
    q4 = questions[3]
    answers[q4.question_id] = next(
        option.option_id for option in q4.options
        if option.option_id != answers[q4.question_id]
    )
    for question in questions:
        checked = client.post(
            f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
            json={"questionId": question.question_id, "answer": answers[question.question_id]},
        )
        assert checked.status_code == 200, checked.text
    submitted = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": answers,
        "idempotencyKey": "a2-m03-wrong-q4",
    })
    assert submitted.status_code == 200, submitted.text
    draft = _scalar(engine, select(sessions.c.analysis_draft).where(sessions.c.id == sid))
    assert all(group["quantity"] != false_count["quantity"] for group in draft["countedGroups"])
    assert false_count["isFictional"] is True
    assert false_count["source"] == "assignedRoleplay"
    with engine.connect() as connection:
        attributes = connection.execute(
            select(scene_objects.c.attributes).where(scene_objects.c.session_id == sid)
        ).scalars().all()
        encountered_terms = connection.execute(
            select(vocabulary_items.c.display_text)
            .join(
                vocabulary_encounters,
                vocabulary_encounters.c.vocabulary_item_id == vocabulary_items.c.id,
            )
            .where(vocabulary_encounters.c.session_id == sid)
        ).scalars().all()
        progress_terms = connection.execute(
            select(vocabulary_items.c.display_text)
            .join(
                user_vocabulary_progress,
                user_vocabulary_progress.c.vocabulary_item_id == vocabulary_items.c.id,
            )
            .where(user_vocabulary_progress.c.user_id == detail.session.user_id)
        ).scalars().all()
    assert all(
        (row or {}).get("quantity") != false_count["quantity"] for row in attributes
    )
    assert false_count["numberWord"] not in " ".join(encountered_terms + progress_terms)


def test_m04_wrong_answers_leave_roleplay_assignment_unchanged(curated):
    engine, client, _repository, sid, detail, *_ = _lesson(curated)
    lesson = next(task for task in detail.tasks if task.public_content.mission_id == "M04")
    key = _answer_key(engine, lesson.id)
    mission_state = key["missionState"]
    wrong_answers = {}
    for question in lesson.public_content.questions:
        expected = key["correctOptionIds"][question.question_id]
        if question.interaction_type == "multipleChoice":
            wrong_answers[question.question_id] = next(
                option.option_id for option in question.options
                if option.option_id != expected
            )
        else:
            wrong_answers[question.question_id] = "not-the-answer"
    for question in lesson.public_content.questions:
        checked = client.post(
            f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
            json={
                "questionId": question.question_id,
                "answer": wrong_answers[question.question_id],
            },
        )
        assert checked.status_code == 200, checked.text
        assert checked.json()["isCorrect"] is False
    assert _answer_key(engine, lesson.id)["missionState"] == mission_state


def test_m04_completion_keeps_ownership_out_of_vocabulary_and_profile_rows(curated):
    engine, client, _repository, sid, detail, *_ = _lesson(curated)
    lesson = next(task for task in detail.tasks if task.public_content.mission_id == "M04")
    key = _answer_key(engine, lesson.id)
    answers = dict(key["correctOptionIds"])
    for question in lesson.public_content.questions:
        checked = client.post(
            f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
            json={"questionId": question.question_id, "answer": answers[question.question_id]},
        )
        assert checked.status_code == 200, checked.text
        assert checked.json()["isCorrect"] is True
    response = client.post(f"/api/v1/tasks/{lesson.id}/attempts", json={
        "inputMode": "vocabularyReview", "answers": answers,
        "idempotencyKey": "a2-m04-ownership",
    })
    assert response.status_code == 200, response.text
    with engine.connect() as connection:
        vocabulary_text = " ".join(map(str, connection.execute(
            select(vocabulary_encounters).where(vocabulary_encounters.c.session_id == sid)
        ).mappings().all()))
        progress_text = " ".join(map(str, connection.execute(
            select(user_vocabulary_progress).where(
                user_vocabulary_progress.c.user_id == detail.session.user_id
            )
        ).mappings().all()))
        profile_text = " ".join(map(str, connection.execute(
            select(language_profiles).where(
                language_profiles.c.id == detail.session.language_profile_id
            )
        ).mappings().all()))
        user_text = " ".join(map(str, connection.execute(
            select(users).where(users.c.id == detail.session.user_id)
        ).mappings().all()))
    for owner in ("Marta", "Léa"):
        assert owner not in vocabulary_text + progress_text + profile_text + user_text
