"""History-weighted mission rotation in the PostgreSQL lesson workflow."""

from uuid import uuid4

from sqlalchemy import select
from test_mission_m01_workflow import _analyzed, _repository, _review, _scalar
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.practice import sessions
from app.schemas.sessions import AddedPracticeObject


def _everything(detail):
    request = _review(detail)
    cup = next(obj for obj in detail.scene_objects if obj.label.casefold() == "cup")
    toy = AddedPracticeObject(id=uuid4(), label="toy", x=0.75, y=0.75)
    return request.model_copy(update={
        "object_counts": {cup.id: 3},
        "added_objects": [toy],
    })


def _planned_missions(engine, session_id):
    draft = _scalar(
        engine,
        select(sessions.c.analysis_draft).where(sessions.c.id == session_id),
    )
    return draft["missionPlan"]


def test_next_lesson_selects_missions_planned_least_on_same_profile_and_photo(curated):
    engine, _owner, profile, client, *_ = curated
    repository = _repository(curated, SceneModel())

    first_id, first_scene = _analyzed(curated, repository)
    repository.review(first_id, profile.id, _everything(first_scene))
    first_plan = _planned_missions(engine, first_id)
    assert [item["missionId"] for item in first_plan] == ["M01", "M02", "M03"]

    abandoned = client.post(f"/api/v1/sessions/{first_id}/abandon")
    assert abandoned.status_code == 200, abandoned.text
    second_id, second_scene = _analyzed(curated, repository)
    repository.review(second_id, profile.id, _everything(second_scene))
    second_plan = _planned_missions(engine, second_id)

    assert [item["missionId"] for item in second_plan] == ["M01", "M04", "M05"]
    assert all(len(item["roleplayFacts"]) == 3 for item in second_plan if item["missionId"] in {
        "M04", "M05",
    })
    detail = repository.get(second_id, profile.id)
    assert {
        task.public_content.mission_id for task in detail.tasks
    } >= {"M04", "M05"}
