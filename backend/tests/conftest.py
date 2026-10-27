"""Shared test fixtures: existing suites exercise the demo-auth fallback."""

import os

import pytest

# Set before app modules are imported so every existing TestClient suite keeps
# using the DEMO_USER_ID fallback instead of requiring bearer tokens.
os.environ.setdefault("AUTH_MODE", "demo")


@pytest.fixture(autouse=True)
def bundled_packs_as_local_experiment(monkeypatch):
    """Mission lessons come only from language packs, and the bundled packs are not yet
    human-reviewed, so tests run them as a local experiment. Pack settings from a local
    ``.env.local`` never leak in; a test may still set its own."""
    from app.language_packs import context

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REGISTER", "everyday")
    for name in ("LINGUINI_LANGUAGE_PACK_DIRS", "LINGUINI_LANGUAGE_PACK_RELEASES",
                 "LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR"):
        monkeypatch.delenv(name, raising=False)
    context._CONTEXTS.clear()
    yield
    context._CONTEXTS.clear()


@pytest.fixture(autouse=True)
def deterministic_upload_analyzer_for_existing_tests(request, monkeypatch):
    if request.node.get_closest_marker("real_upload_analysis") is not None:
        monkeypatch.setenv("AI_MODE", "demo")
        monkeypatch.delenv("AI_OPENROUTER_API_KEY", raising=False)
        return

    from app.repositories.postgres.workflow import PostgresWorkflowRepository
    from app.services.scene_analysis import DeterministicSceneAnalyzer

    monkeypatch.setattr(
        PostgresWorkflowRepository,
        "_uploaded_fallback_analyzer",
        lambda self: DeterministicSceneAnalyzer(self.engine),
    )


@pytest.fixture
def regular_lesson(monkeypatch):
    """Exercise the regular lesson, which only profiles without implemented missions use.

    A mission profile rejects a scene no mission fits, so suites that confirm a thin
    scene to test shared task machinery opt out of A1 missions with this fixture.
    """
    from app.services import mission_eligibility

    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", ())
