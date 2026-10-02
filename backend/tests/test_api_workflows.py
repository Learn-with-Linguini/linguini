"""Service/API regressions using PostgreSQL instead of the retired JSON adapters."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.main import create_app


def test_profile_preferences_and_restart(database):
    _, _, profile, client = database
    settings = {
        "displayName": "Updated learner",
        "learningGoal": "Practise conversation",
        "microphoneEnabled": False,
        "cameraEnabled": False,
        "onboardingCompleted": True,
    }
    response = client.patch("/api/v1/me", json=settings)
    assert response.status_code == 200
    for key, value in settings.items():
        assert response.json()[key] == value
    language = {"proficiencyLevel": "B1", "dailyGoalMinutes": 25}
    assert (
        client.patch(f"/api/v1/me/language-profiles/{profile.id}", json=language).status_code == 200
    )
    with TestClient(create_app()) as restarted:
        assert restarted.get("/api/v1/me").json() == response.json()
        saved = restarted.get("/api/v1/me/language-profiles").json()[0]
        assert all(saved[key] == value for key, value in language.items())


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "PUT", "DELETE"])
def test_cors_preflight(database, method):
    *_, client = database
    response = client.options(
        "/api/v1/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options(
        "/api/v1/me",
        headers={
            "Origin": "https://unlisted.example",
            "Access-Control-Request-Method": method,
        },
    )
    assert denied.status_code == 400


def test_missing_user_and_scene_errors(database, monkeypatch):
    *_, client = database
    assert client.get("/api/v1/preloaded-scenes/unknown").status_code == 404
    monkeypatch.setenv("DEMO_USER_ID", str(uuid4()))
    for path in ["me", "me/progress", "me/vocabulary", "me/language-profiles"]:
        assert client.get(f"/api/v1/{path}").status_code == 404


def test_server_rejects_forged_awards_and_unknown_events(database):
    _, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    client.post(f"/api/v1/sessions/{sid}/analyze")
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    client.put(
        f"/api/v1/sessions/{sid}/review",
        json={"acceptedObjectIds": [detail["sceneObjects"][0]["id"]]},
    )
    detail = client.get(f"/api/v1/sessions/{sid}").json()
    task_id = detail["tasks"][1]["id"]
    response = client.post(
        f"/api/v1/tasks/{task_id}/attempts",
        json={"inputMode": "text", "text": "answer", "score": 1, "xp": 9999},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/me/progress").json()["xp"] == 0
