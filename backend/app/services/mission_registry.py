"""Generation and task building for each implemented mission lesson."""

from collections.abc import Callable
from dataclasses import dataclass

from app.ai.features.learning_tasks.mission import M01_GENERATION, MissionGeneration
from app.ai.features.learning_tasks.mission_m02 import M02_GENERATION
from app.services.mission_lessons import m01_payload, mission_lesson_task
from app.services.mission_lessons_m02 import m02_lesson_task, m02_payload


@dataclass(frozen=True)
class MissionLessonSpec:
    payload: Callable[..., dict]
    generation: MissionGeneration
    task: Callable


def _m01_payload(mission, language, objects, _relations, words, translated_scene):
    return m01_payload(mission, language, objects, words, translated_scene)


MISSION_LESSONS = {
    "M01": MissionLessonSpec(_m01_payload, M01_GENERATION, mission_lesson_task),
    "M02": MissionLessonSpec(m02_payload, M02_GENERATION, m02_lesson_task),
}
