"""Generation and task building for each implemented mission lesson."""

from collections.abc import Callable
from dataclasses import dataclass

from app.ai.features.learning_tasks.mission import MissionGeneration
from app.ai.features.learning_tasks.mission_a0 import A0_GENERATIONS
from app.ai.features.learning_tasks.mission_a0_situations import A0_SITUATION_GENERATIONS
from app.ai.features.learning_tasks.mission_a2 import A2_GENERATIONS
from app.ai.features.learning_tasks.mission_m01 import M01_GENERATION
from app.ai.features.learning_tasks.mission_m02 import M02_GENERATION
from app.ai.features.learning_tasks.mission_m03 import M03_GENERATION
from app.ai.features.learning_tasks.mission_m04 import M04_GENERATION
from app.ai.features.learning_tasks.mission_m05 import M05_GENERATION
from app.missions import get_mission
from app.services.mission_lessons_a0 import a0_lesson_task, a0_payload, a0_ready
from app.services.mission_lessons_a0_situations import (
    a0_situation_lesson_task,
    build_a0_situation_payload,
)
from app.services.mission_lessons_a2 import a2_mission_spec
from app.services.mission_lessons_m01 import m01_lesson_task, m01_payload
from app.services.mission_lessons_m02 import m02_lesson_task, m02_payload
from app.services.mission_lessons_m03 import m03_lesson_task, m03_payload
from app.services.mission_lessons_m04 import m04_lesson_task, m04_payload, m04_ready
from app.services.mission_lessons_m05 import m05_lesson_task, m05_payload, m05_ready


@dataclass(frozen=True)
class MissionLessonSpec:
    """``payload(mission, language, objects, relations, words, translated_scene, counts,
    progress, session_id, review_markers=None, context=None)``;
    ``ready(payload)`` is false when the confirmed facts give no reviewed content."""

    payload: Callable[..., dict]
    generation: MissionGeneration
    task: Callable
    ready: Callable[[dict], bool] = lambda payload: True
    # The definition version new lessons are built for; older plans are rebuilt at it.
    content_version: int = 1


def _m01_payload(
    mission, language, objects, _relations, words, translated_scene, _counts, progress,
    session_id, review_markers=None, context=None,
):
    return m01_payload(mission, language, objects, words, translated_scene, progress, session_id)


def _m02_payload(
    mission, language, objects, relations, words, translated_scene, _counts, progress,
    session_id, review_markers=None, context=None,
):
    return m02_payload(
        mission, language, objects, relations, words, translated_scene, progress, session_id,
        review_markers,
    )


def _m03_payload(
    mission, language, objects, relations, words, translated_scene, counts, progress,
    session_id, review_markers=None, context=None,
):
    return m03_payload(
        mission, language, objects, relations, words, translated_scene, counts,
        progress, session_id,
    )


def _m04_payload(
    mission, language, objects, relations, words, translated_scene, _counts, _progress,
    session_id, review_markers=None, context=None,
):
    if review_markers is not None:
        context = {**(context or {}), "review_markers": review_markers}
    return m04_payload(
        mission, language, objects, words, translated_scene, session_id, context
    )


def _m05_payload(
    mission, language, objects, relations, words, translated_scene, _counts, _progress,
    session_id, review_markers=None, context=None,
):
    if review_markers is not None:
        context = {**(context or {}), "review_markers": review_markers}
    return m05_payload(
        mission, language, objects, words, translated_scene, session_id, context
    )


def _a0_situation_payload(
    mission, language, objects, relations, words, translated_scene, counts, progress,
    session_id, review_markers=None, context=None,
):
    if review_markers is not None:
        context = {**(context or {}), "review_markers": review_markers}
    payload = a0_payload(
        mission, language, objects, relations, words, translated_scene, counts,
        progress, session_id, review_markers=review_markers, context=context,
    )
    return build_a0_situation_payload(payload)


MISSION_LESSONS = {
    "M01": MissionLessonSpec(
        _m01_payload, M01_GENERATION, m01_lesson_task,
        lambda payload: len(payload["pairs"]) == 2,
    ),
    "M02": MissionLessonSpec(
        _m02_payload, M02_GENERATION, m02_lesson_task,
        lambda payload: bool(payload["selected"]),
        content_version=2,
    ),
    "M03": MissionLessonSpec(
        _m03_payload, M03_GENERATION, m03_lesson_task,
        lambda payload: payload["group"] is not None,
    ),
    "M04": MissionLessonSpec(
        _m04_payload, M04_GENERATION, m04_lesson_task, m04_ready,
    ),
    "M05": MissionLessonSpec(
        _m05_payload, M05_GENERATION, m05_lesson_task, m05_ready,
    ),
}


# A0 (pre-A1) scene missions, keyed ``A0:Mxx`` and listed in catalogue order.
A0_MISSION_LESSONS = {
    f"A0:{mission_id}": (
        MissionLessonSpec(
            _a0_situation_payload,
            A0_SITUATION_GENERATIONS[mission_id],
            a0_situation_lesson_task,
            lambda payload: len(payload["approvedObjects"]) >= 2
            and len(payload.get("questions", [])) == 6,
        )
        if mission_id in A0_SITUATION_GENERATIONS
        else MissionLessonSpec(
            a0_payload, A0_GENERATIONS[mission_id], a0_lesson_task, a0_ready,
        )
    )
    for mission_id in ("M01", "M02", "M03", "M04", "M05", "M13")
}


A2_MISSION_LESSONS = {
    f"A2:{mission_id}": MissionLessonSpec(
        a2_mission_spec(mission_id)[0], A2_GENERATIONS[mission_id],
        a2_mission_spec(mission_id)[1], a2_mission_spec(mission_id)[2],
    )
    for mission_id in ("M01", "M02", "M03", "M04")
}


def registry_key(mission):
    """The level-qualified mission key, e.g. ``A0:M01``."""
    return f"{mission.practice_level}:{mission.mission_id}"


def lesson_spec(mission):
    """Return the level-qualified lesson builder, falling back to the A1 spec."""
    key = registry_key(mission)
    return (
        A0_MISSION_LESSONS.get(key)
        or A2_MISSION_LESSONS.get(key)
        or MISSION_LESSONS[mission.mission_id]
    )


def lesson_mission(mission):
    """``mission`` at the version its lessons are now built for, keeping saved plans valid."""
    spec = lesson_spec(mission)
    if mission.content_version == spec.content_version:
        return mission
    return get_mission(mission.mission_id, mission.practice_level, spec.content_version)
