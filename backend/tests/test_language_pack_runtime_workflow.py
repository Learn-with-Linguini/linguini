"""Spanish persistence/completion integration; mocked provider, disposable PostgreSQL only."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_language_pack_runtime import PACK, MockSpanishProvider
from test_mission_m01_workflow import _analyzed, _answer_key, _attempt, _scalar
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, services
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.tasks import task_attempts
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.schemas.sessions import AddedPracticeObject, ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest
from app.services import mission_eligibility


class MockWorkflowModel(SceneModel):
    def __init__(self):
        super().__init__()
        self.pack_provider = MockSpanishProvider()

    def generate(self, request, **options):
        if request.json_schema_name in {
            "language_pack_candidates_v1", "language_vocabulary_proposals",
            "language_content_review",
        }:
            return self.pack_provider.generate(request)
        response = super().generate(request, **options)
        if request.json_schema_name == "scene_translation_v1":
            body = json.loads(response.output_text)
            for field in body.values():
                for term in field:
                    term["translation"] = {"chair": "silla", "white": "blanca"}.get(
                        term["source"], term["translation"]
                    )
                    term["native_display"] = " ".join(filter(None, [
                        term.get("article"), term["translation"],
                    ]))
            return replace(response, output_text=json.dumps(body, ensure_ascii=False))
        return response


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_pack_generation_persists_grades_and_completes_once(curated, monkeypatch, level):
    engine, owner, profile, client, *_ = curated
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACK))
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, level, (("M01", level, 1),))
    with engine.begin() as connection:
        connection.execute(
            update(language_profiles)
            .where(language_profiles.c.id == profile.id)
            .values(proficiency_level=level)
        )
    model = MockWorkflowModel()
    feature = services(model)
    repository = PostgresWorkflowRepository(
        engine,
        owner.id,
        translator=feature["translation"],
        learning_task_generator=feature["lessons"],
    )
    sid, analyzed = _analyzed(curated, repository)
    cup = next(obj for obj in analyzed.scene_objects if obj.label == "cup")
    table = next(obj for obj in analyzed.scene_objects if obj.label == "table")
    repository.review(
        sid,
        profile.id,
        ReviewPracticeRequest(
            accepted_object_ids=[obj.id for obj in analyzed.scene_objects],
            added_objects=[AddedPracticeObject(id=uuid4(), label="chair", x=0.75, y=0.5)],
            object_attributes={cup.id: {"color": "red"}, table.id: {"color": "white"}},
            relations=analyzed.scene_object_relations,
        ),
    )
    detail = repository.get(sid, profile.id)
    lesson = next(task for task in detail.tasks if task.kind == "grammarLesson")
    assert lesson.public_content.practice_level == level
    assert lesson.public_content.language_context.language_code == "es"
    intro = next(t for t in detail.tasks if t.kind == "vocabularyIntroduction")
    assert intro.public_content.language_context == lesson.public_content.language_context
    restored = repository.get(sid, profile.id)
    assert next(t for t in restored.tasks if t.id == lesson.id).public_content.language_context == (
        lesson.public_content.language_context
    )
    assert len(model.pack_provider.requests) == 1
    answers = _answer_key(engine, lesson.id)["correctOptionIds"]
    if lesson.public_content.check_each_question:
        for question in lesson.public_content.questions:
            checked = client.post(
                f"/api/v1/tasks/{lesson.id}/check-lesson-answer",
                json={
                    "questionId": question.question_id,
                    "answer": answers[question.question_id],
                },
            )
            assert checked.status_code == 200, checked.text
            assert checked.json()["isCorrect"]
    first = _attempt(client, lesson, answers)
    assert first.status_code == 200, first.text
    assert all(
        item["outcome"] == "correct"
        for item in first.json()["attempt"]["evaluationDetails"]["questionOutcomes"]
    )
    repeat = _attempt(client, lesson, answers)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
    assert (
        _scalar(
            engine,
            select(func.count())
            .select_from(task_attempts)
            .where(task_attempts.c.session_task_id == lesson.id),
        )
        == 1
    )
    for task in repository.get(sid, profile.id).tasks:
        if task.status not in {"completed", "skipped"}:
            repository.task_action(task.id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"
    assert (
        _scalar(
            engine,
            select(func.count())
            .select_from(xp_events)
            .where(xp_events.c.session_id == sid, xp_events.c.event_type == "sessionCompleted"),
        )
        == 1
    )
