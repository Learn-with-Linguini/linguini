"""Level-gated mission catalogues and history-weighted mission rotation."""

import pytest

from app.schemas.enums import SessionMode
from app.services import mission_eligibility
from app.services.mission_eligibility import Eligibility, lesson_missions, plan_missions


def test_a1_lesson_catalogue_contains_missions_m01_through_m05():
    missions = lesson_missions(
        SessionMode.LESSON,
        {"proficiency_level": "A1", "target_language_code": "es"},
    )
    assert [mission.mission_id for mission in missions] == [
        "M01", "M02", "M03", "M04", "M05",
    ]


def test_proficiency_level_is_trimmed_and_case_normalized():
    missions = lesson_missions(
        SessionMode.LESSON,
        {"proficiency_level": " a1 ", "target_language_code": "es"},
    )
    assert [mission.mission_id for mission in missions] == [
        "M01", "M02", "M03", "M04", "M05",
    ]


@pytest.mark.parametrize("level", ["B1"])
def test_other_levels_are_not_eligible_even_after_onboarding(level):
    missions = lesson_missions(
        SessionMode.LESSON,
        {
            "proficiency_level": level,
            "target_language_code": "es",
            "onboarding_completed": True,
        },
    )
    assert missions == []


def test_fresh_profiles_keep_catalogue_order(monkeypatch):
    monkeypatch.setattr(
        mission_eligibility,
        "photo_eligibility",
        lambda *_args: Eligibility(True),
    )
    candidates = lesson_missions(
        SessionMode.LESSON,
        {"proficiency_level": "A1", "target_language_code": "es"},
    )
    planned = plan_missions(candidates, [], [], history=[])
    assert [mission.mission_id for mission in planned] == ["M01", "M02", "M03"]


def test_plan_rotation_prioritizes_least_planned_then_returns_catalogue_order(monkeypatch):
    monkeypatch.setattr(
        mission_eligibility,
        "photo_eligibility",
        lambda *_args: Eligibility(True),
    )
    candidates = lesson_missions(
        SessionMode.LESSON,
        {"proficiency_level": "A1", "target_language_code": "es"},
    )
    planned = plan_missions(
        candidates,
        [],
        [],
        history=["M01", "M02", "M03"],
    )
    assert [mission.mission_id for mission in planned] == ["M01", "M04", "M05"]
