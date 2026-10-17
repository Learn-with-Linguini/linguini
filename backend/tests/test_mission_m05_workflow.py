"""PostgreSQL workflow coverage for M05 persistence, grading and isolation."""

import pytest
from mission_workflow_helpers import (
    assert_grading_and_isolation,
    assert_tampered_facts_skip,
    review_lesson,
)
from test_postgres_sessions import database as database
from test_preloaded_templates_workflow import curated as curated

from app.services import mission_eligibility

M05_ONLY = (("M05", "A1", 1),)


@pytest.fixture(autouse=True)
def only_m05(monkeypatch):
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", M05_ONLY)


def test_m05_plan_facts_markers_and_resumed_content_are_persisted(curated):
    _repo, _session_id, detail, task, markers, facts = review_lesson(curated, "M05")
    assert detail.session.analysis_draft["missionPlan"] == [{
        "missionId": "M05",
        "practiceLevel": "A1",
        "contentVersion": 1,
        "roleplayFacts": facts,
    }]
    assert all(fact["source"] == "assignedRoleplay" and fact["isFictional"] for fact in facts)
    assert {fact["preference"] for fact in facts} >= {"like", "dislike"}
    assert all(
        "roleplayFacts" not in (obj.attributes or {})
        for obj in detail.scene_objects
    )
    assert len(markers) == len(detail.scene_objects)
    assert len(task.public_content.questions) == 4
    assert all(question.roleplay_premise for question in task.public_content.questions)


def test_m05_is_omitted_with_only_two_confirmed_objects(curated):
    _repo, _session_id, _detail, task, _markers, facts = review_lesson(
        curated,
        "M05",
        confirmed_object_limit=2,
        add_missing_roleplay_object=False,
        expect_omitted=True,
    )
    assert task is None
    assert facts == []


@pytest.mark.parametrize("scenario", ["partial", "incorrect"])
def test_m05_attempts_grade_restore_and_remain_idempotent(curated, scenario):
    assert_grading_and_isolation(curated, "M05", scenario)


def test_m05_correct_attempt_does_not_pollute_learner_data_and_awards_xp_once(curated):
    assert_grading_and_isolation(curated, "M05", "correct")


def test_tampered_m05_facts_skip_only_m05_with_invalid_roleplay(curated):
    assert_tampered_facts_skip(curated, "M05")
