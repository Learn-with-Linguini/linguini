"""A0 mission lessons through the PostgreSQL workflow: persistence, grading, XP and evidence."""

import pytest
from sqlalchemy import func, select, update
from test_mission_m01_workflow import (
    _analyzed,
    _answer_key,
    _attempt,
    _lesson,
    _repository,
    _review,
    _scalar,
)
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import vocabulary_encounters
from app.repositories.postgres.xp import xp_events


@pytest.fixture
def beginner(curated):
    engine, owner, profile, *_ = curated
    with engine.begin() as connection:
        connection.execute(update(language_profiles).where(
            language_profiles.c.id == profile.id
        ).values(proficiency_level="A0"))
        # Onboarding has no say in which missions a profile gets.
        connection.execute(update(users).where(
            users.c.id == owner.id
        ).values(onboarding_completed=False))
    return curated


def _a0_lessons(detail):
    return [task for task in detail.tasks if task.kind == "grammarLesson"
            and task.public_content.practice_level == "A0"]


def test_a0_profiles_get_persisted_a0_lessons(beginner):
    engine, *_ = beginner
    repository, sid, detail = _lesson(beginner)
    lessons = _a0_lessons(detail)
    assert lessons, detail.session.analysis_draft
    assert {task.public_content.mission_id for task in lessons} <= {
        "M01", "M02", "M03", "M04", "M05", "M13",
    }
    for task in lessons:
        content = task.public_content
        assert len(content.questions) == 6
        assert len({q.section for q in content.questions}) == 2
        stored = _scalar(engine, select(session_tasks.c.public_content).where(
            session_tasks.c.id == task.id
        ))
        assert stored["practiceLevel"] == "A0" and "Pre-A1" not in str(stored)
        key = _answer_key(engine, task.id)
        assert set(key["correctOptionIds"]) == {q.question_id for q in content.questions}
    # Refreshing reads the saved lesson; nothing is regenerated.
    refreshed = repository.get(sid, detail.session.language_profile_id)
    assert [t.public_content for t in _a0_lessons(refreshed)] == [
        t.public_content for t in lessons
    ]


def test_review_assigns_pretend_ownership_and_preference_scenarios(beginner):
    _engine, _owner, profile, *_ = beginner
    repository = _repository(beginner, SceneModel())
    sid, analyzed = _analyzed(beginner, repository)
    first, second = analyzed.scene_objects[:2]
    repository.review(sid, profile.id, _review(analyzed))
    reviewed = repository.get(sid, profile.id)
    assert reviewed.mission_choices is None
    assert "missionChoices" not in reviewed.session.analysis_draft
    lessons = {task.public_content.mission_id: task for task in _a0_lessons(reviewed)}
    assert {"M04", "M05"} <= lessons.keys(), reviewed.session.analysis_draft.get("missionPlan")
    assert lessons["M04"].public_content.mission_snapshot.owned_object_id == first.id
    assert lessons["M04"].public_content.mission_snapshot.pretend is True
    assert lessons["M05"].public_content.mission_snapshot.preference_object_ids == [second.id]
    restored = repository.get(sid, profile.id)
    assert {"M04", "M05"} <= {
        task.public_content.mission_id for task in _a0_lessons(restored)
    }


def test_a0_grading_is_idempotent_and_awards_once(beginner):
    engine, _owner, profile, client, *_ = beginner
    repository, sid, detail = _lesson(beginner)
    lesson = _a0_lessons(detail)[0]
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    first = _attempt(client, lesson, correct, key="a0-answer")
    assert first.status_code == 200, first.text
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    encounters = select(func.count()).select_from(vocabulary_encounters).where(
        vocabulary_encounters.c.session_task_id == lesson.id
    )
    awarded, recorded = _scalar(engine, xp), _scalar(engine, encounters)
    assert awarded >= 1
    repeat = _attempt(client, lesson, correct, key="a0-answer")
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
    assert (_scalar(engine, xp), _scalar(engine, encounters)) == (awarded, recorded)
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 1
    details = first.json()["attempt"]["evaluationDetails"]
    assert details["questionResults"] == {qid: True for qid in correct}
    restored = client.get(f"/api/v1/tasks/{lesson.id}/latest-attempt").json()["attempt"]
    assert restored["answers"] == correct
    assert restored["reviewDetails"]["questionResults"] == details["questionResults"]
    assert restored["feedback"] == first.json()["attempt"]["feedback"]["message"]
    resumed = next(t for t in repository.get(sid, profile.id).tasks if t.id == lesson.id)
    assert resumed.status == "completed"
    assert [[o.option_id for o in q.options] for q in resumed.public_content.questions] == [
        [o.option_id for o in q.options] for q in lesson.public_content.questions
    ]


def test_wrong_answers_are_graded_from_the_saved_key(beginner):
    engine, _owner, _profile, client, *_ = beginner
    _repository_, _sid, detail = _lesson(beginner)
    lesson = _a0_lessons(detail)[0]
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    wrong = {
        q.question_id: next(o.option_id for o in q.options if o.option_id != correct[q.question_id])
        if q.interaction_type == "multipleChoice" else " ".join(reversed(q.token_bank))
        for q in lesson.public_content.questions
    }
    response = _attempt(client, lesson, wrong, key="a0-wrong")
    assert response.status_code == 200, response.text
    results = response.json()["attempt"]["evaluationDetails"]["questionResults"]
    assert not any(results.values())
