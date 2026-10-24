"""Lessons come only from language packs: new, resumed and old sessions, without a database."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.api.learning_errors import register_learning_errors
from app.language_packs.context import resolve_language_context
from app.missions import get_mission
from app.repositories.postgres.workflow import (
    PostgresWorkflowRepository,
    session_language_context,
)
from app.repositories.practice import LessonLanguageUnavailableError
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import lesson_mission


def _profile(language="es"):
    return {"target_language_code": language, "proficiency_level": "A1", "language_register": None}


def _session(draft=None):
    return SimpleNamespace(
        mode=SessionMode.LESSON, analysis_draft=draft or {}, session_summary=None,
    )


def test_a_new_lesson_needs_a_language_with_a_ready_pack():
    PostgresWorkflowRepository._check_lesson_language(_profile("es"))
    with pytest.raises(LessonLanguageUnavailableError):
        PostgresWorkflowRepository._check_lesson_language(_profile("it"))


def test_an_unavailable_language_is_a_structured_409():
    app = FastAPI()
    register_learning_errors(app)

    @app.post("/sessions")
    def create():
        raise LessonLanguageUnavailableError("No lessons for this language yet.")

    response = TestClient(app).post("/sessions")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_language_unavailable"


def test_every_lesson_translates_with_its_pack_and_never_without_one():
    claim = SimpleNamespace(
        session_id=uuid4(), profile=_profile("it"), session=_session(), objects=[],
        relations=[], language_context=None, missions=[get_mission("M01", "A1", 1)],
    )
    repository = SimpleNamespace(translator=object())
    with pytest.raises(LearningTaskGenerationError, match="No language pack"):
        PostgresWorkflowRepository._generate_tasks(repository, claim)
    # Planned missions need the pack translator; only a lesson without missions may run
    # without one (the deterministic default lesson, when no AI is configured).
    claim.language_context = resolve_language_context("es")
    with pytest.raises(LearningTaskGenerationError, match="scene translations"):
        PostgresWorkflowRepository._generate_tasks(SimpleNamespace(translator=None), claim)


def test_a_planned_mission_without_its_pack_fails_instead_of_using_another_builder():
    claim = SimpleNamespace(
        profile=_profile("it"), language_context=None, missions=[get_mission("M01", "A1", 1)],
    )
    with pytest.raises(LearningTaskGenerationError, match="no language pack lesson"):
        PostgresWorkflowRepository._mission_lessons(SimpleNamespace(), claim, [], [], [], None, [])


def test_plans_saved_at_an_old_content_version_build_at_the_pack_version():
    assert lesson_mission(get_mission("M02", "A1", 1)).content_version == 2
    current = get_mission("M01", "A1", 1)
    assert lesson_mission(current) is current


def test_a_session_saved_without_a_snapshot_uses_the_profiles_pack():
    context = session_language_context(_session(), _profile("es"))
    assert context.display.language_code == "es"


def test_a_saved_snapshot_restores_while_its_pack_is_still_ready():
    snapshot = resolve_language_context("es").snapshot()
    restored = session_language_context(_session({"languageContext": snapshot}), _profile("es"))
    assert restored.ready_missions == tuple(snapshot["readyMissions"])


def test_a_saved_pack_that_is_no_longer_ready_refuses_the_session(monkeypatch):
    snapshot = resolve_language_context("es").snapshot()
    # The saved pack was a local experiment; without it the release gates now fail.
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "false")
    with pytest.raises(LessonLanguageUnavailableError):
        session_language_context(_session({"languageContext": snapshot}), _profile("es"))
