"""Shared test fixtures: existing suites exercise the demo-auth fallback."""

import os

import pytest

# Set before app modules are imported so every existing TestClient suite keeps
# using the DEMO_USER_ID fallback instead of requiring bearer tokens.
os.environ.setdefault("AUTH_MODE", "demo")


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
