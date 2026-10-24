"""Planning and role-play rules for the A0 M04 and M05 situation lessons.

Pack-built lesson content is covered by the language-pack tests.
"""

from uuid import uuid4

import pytest
from test_mission_a0 import LABELS, _objects

from app.missions import get_mission
from app.services.mission_eligibility import (
    lesson_missions,
    photo_eligibility,
    plan_missions,
    provisional_mission_focus,
)
from app.services.mission_roleplay import assign_roleplay


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_final_a0_eligibility_requires_a_confirmed_choice(mission_id):
    mission = get_mission(mission_id, "A0", 1)
    objects = _objects(["cup", "book"])
    assert photo_eligibility(mission, objects).eligible
    assert not photo_eligibility(mission, objects, mission_choices={}).eligible
    if mission_id == "M04":
        choices = {"ownership": {"scene_object_id": str(objects[0].id)}}
    else:
        choices = {"preference": {
            "scene_object_ids": [str(objects[0].id)],
            "chosen_object_id": None,
            "reaction": "like",
        }}
    assert photo_eligibility(mission, objects, mission_choices=choices).eligible


def test_provisional_plan_surfaces_both_opt_in_a0_situations_within_final_cap():
    candidates = lesson_missions(
        "lesson", {"proficiency_level": "A0", "target_language_code": "es"},
    )
    objects = _objects(["cup", "book"])
    provisional, _selected = provisional_mission_focus(candidates, objects, [])
    provisional_ids = [mission.mission_id for mission in provisional]
    assert {"M04", "M05"} <= set(provisional_ids)
    candidate_order = {
        (mission.mission_id, str(mission.practice_level), mission.content_version): index
        for index, mission in enumerate(candidates)
    }
    planned_order = [
        candidate_order[
            (mission.mission_id, str(mission.practice_level), mission.content_version)
        ]
        for mission in provisional
    ]
    assert planned_order == sorted(planned_order)

    choices = {
        "ownership": {"scene_object_id": str(objects[0].id)},
        "preference": {
            "scene_object_ids": [str(objects[1].id)],
            "reaction": "like",
        },
    }
    final = plan_missions(candidates, objects, [], mission_choices=choices)
    final_ids = {mission.mission_id for mission in final}
    assert {"M04", "M05"} <= final_ids
    assert len(final) <= 3


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_missions_never_get_a1_roleplay_facts(mission_id):
    objects = _objects(LABELS[:3])
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    assert assign_roleplay(get_mission(mission_id, "A0", 1), uuid4(), objects, markers) == []
    assert len(assign_roleplay(get_mission(mission_id, "A1", 1), uuid4(), objects, markers)) == 3






