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
from app.services.mission_roleplay import assign_a0_scenario, assign_roleplay


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_final_a0_eligibility_needs_no_choice_but_checks_a_sent_one(mission_id):
    mission = get_mission(mission_id, "A0", 1)
    objects = _objects(["cup", "book"])
    assert photo_eligibility(mission, objects).eligible
    # Without a choice the plan assigns a scenario, so the photo is enough.
    assert photo_eligibility(mission, objects, mission_choices={}).eligible
    assert not photo_eligibility(mission, objects[:1], mission_choices={}).eligible
    if mission_id == "M04":
        choices = {"ownership": {"scene_object_id": str(objects[0].id)}}
        elsewhere = {"ownership": {"scene_object_id": str(uuid4())}}
    else:
        choices = {"preference": {
            "scene_object_ids": [str(objects[0].id)],
            "chosen_object_id": None,
            "reaction": "like",
        }}
        elsewhere = {"preference": {"scene_object_ids": [str(uuid4())], "reaction": "like"}}
    assert photo_eligibility(mission, objects, mission_choices=choices).eligible
    assert not photo_eligibility(mission, objects, mission_choices=elsewhere).eligible


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_scenario_is_stable_pretend_and_only_for_a0(mission_id):
    objects = _objects(LABELS[:3])
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    session_id = uuid4()
    a0 = get_mission(mission_id, "A0", 1)
    facts = assign_a0_scenario(a0, session_id, objects, markers)
    assert facts == assign_a0_scenario(a0, session_id, objects, markers)
    ids = {str(obj.id) for obj in objects}
    if mission_id == "M04":
        assert facts["ownedObjectId"] in ids and facts["pretend"] is True
    else:
        preference = facts["preference"]
        compared = preference["sceneObjectIds"]
        assert len(set(compared)) == 2 and set(compared) <= ids
        assert preference["chosenObjectId"] == compared[0]
        assert preference["reaction"] in {"like", "dislike"} and preference["pretend"] is True
    assert assign_a0_scenario(get_mission(mission_id, "A1", 1), session_id, objects,
                              markers) is None
    # Two different, marked objects are needed.
    assert assign_a0_scenario(a0, session_id, objects[:1], markers) is None
    assert assign_a0_scenario(a0, session_id, objects, {}) is None


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
    # Without choices (no review screen sends them) they can still be planned.
    unchosen = {mission.mission_id for mission in plan_missions(
        candidates, objects, [], mission_choices={})}
    assert unchosen & {"M04", "M05"}


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_missions_never_get_a1_roleplay_facts(mission_id):
    objects = _objects(LABELS[:3])
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    assert assign_roleplay(get_mission(mission_id, "A0", 1), uuid4(), objects, markers) == []
    assert len(assign_roleplay(get_mission(mission_id, "A1", 1), uuid4(), objects, markers)) == 3






