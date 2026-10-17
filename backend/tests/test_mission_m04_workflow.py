"""PostgreSQL workflow coverage for M04 persistence, grading and isolation."""

from uuid import uuid4, uuid5

import pytest
from mission_workflow_helpers import (
    assert_grading_and_isolation,
    assert_tampered_facts_skip,
    review_lesson,
)
from sqlalchemy import select, update
from test_mission_m01_workflow import _review
from test_postgres_sessions import database as database
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.practice import sessions
from app.schemas.sessions import AddedPracticeObject
from app.services import mission_eligibility

M04_ONLY = (("M04", "A1", 1),)


@pytest.fixture(autouse=True)
def only_m04(monkeypatch):
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", M04_ONLY)


def test_m04_plan_facts_markers_and_resumed_content_are_persisted(curated):
    _repo, session_id, detail, task, markers, facts = review_lesson(curated, "M04")
    assert detail.session.analysis_draft["missionPlan"] == [{
        "missionId": "M04",
        "practiceLevel": "A1",
        "contentVersion": 1,
        "roleplayFacts": facts,
    }]
    assert all(fact["source"] == "assignedRoleplay" and fact["isFictional"] for fact in facts)
    assert all(
        "roleplayFacts" not in (obj.attributes or {})
        for obj in detail.scene_objects
    )
    assert len(markers) == len(detail.scene_objects)
    assert len(task.public_content.questions) == 4
    assert all(question.roleplay_premise for question in task.public_content.questions)


def test_m04_is_omitted_with_only_two_confirmed_objects(curated):
    _repo, _session_id, _detail, task, _markers, facts = review_lesson(
        curated,
        "M04",
        confirmed_object_limit=2,
        add_missing_roleplay_object=False,
        expect_omitted=True,
    )
    assert task is None
    assert facts == []


def test_added_object_uses_marker_after_original_scene_objects(curated):
    added = AddedPracticeObject(id=uuid4(), label="toy", x=0.75, y=0.75)
    _repo, session_id, detail, _task, markers, _facts = review_lesson(
        curated, "M04", added_objects=[added]
    )
    manual_id = uuid5(session_id, "manual:" + str(added.id))
    assert markers[str(manual_id)] == len(detail.scene_objects)


def test_replanning_preserves_unknown_mission_plan_entry_fields(curated):
    engine, _owner, profile, *_ = curated
    repo, session_id, detail, _task, _markers, _facts = review_lesson(curated, "M04")
    with engine.begin() as connection:
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == session_id)
        ).scalar_one()
        draft["missionPlan"][0]["futureField"] = {"preserve": True}
        connection.execute(
            update(sessions).where(sessions.c.id == session_id).values(analysis_draft=draft)
        )
    repo.review(session_id, profile.id, _review(detail))
    replanned = repo.get(session_id, profile.id)
    assert replanned.session.analysis_draft["missionPlan"][0]["futureField"] == {
        "preserve": True
    }


@pytest.mark.parametrize("scenario", ["partial", "incorrect"])
def test_m04_attempts_grade_restore_and_remain_idempotent(curated, scenario):
    assert_grading_and_isolation(curated, "M04", scenario)


def test_m04_correct_attempt_does_not_pollute_learner_data_and_awards_xp_once(curated):
    assert_grading_and_isolation(curated, "M04", "correct")


def test_tampered_m04_facts_skip_only_m04_with_invalid_roleplay(curated):
    assert_tampered_facts_skip(curated, "M04")
