"""Generation and task building for each implemented mission lesson."""

from collections.abc import Callable
from dataclasses import dataclass

from app.ai.features.learning_tasks.mission import MissionGeneration
from app.ai.features.learning_tasks.mission_m01 import M01_GENERATION
from app.ai.features.learning_tasks.mission_m02 import M02_GENERATION
from app.ai.features.learning_tasks.mission_m03 import M03_GENERATION
from app.services.mission_lessons_m01 import m01_lesson_task, m01_payload
from app.services.mission_lessons_m02 import m02_lesson_task, m02_payload
from app.services.mission_lessons_m03 import m03_lesson_task, m03_payload


@dataclass(frozen=True)
class MissionLessonSpec:
    """``payload(mission, language, objects, relations, words, translated_scene, counts)``;
    ``ready(payload)`` is false when the confirmed facts give no reviewed content."""

    payload: Callable[..., dict]
    generation: MissionGeneration
    task: Callable
    ready: Callable[[dict], bool] = lambda payload: True


def _m01_payload(mission, language, objects, _relations, words, translated_scene, _counts):
    return m01_payload(mission, language, objects, words, translated_scene)


def _m02_payload(mission, language, objects, relations, words, translated_scene, _counts):
    return m02_payload(mission, language, objects, relations, words, translated_scene)


MISSION_LESSONS = {
    "M01": MissionLessonSpec(_m01_payload, M01_GENERATION, m01_lesson_task),
    "M02": MissionLessonSpec(_m02_payload, M02_GENERATION, m02_lesson_task),
    "M03": MissionLessonSpec(
        m03_payload, M03_GENERATION, m03_lesson_task,
        lambda payload: payload["group"] is not None,
    ),
}
