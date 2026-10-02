from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_contains_core_workflow_routes() -> None:
    paths = app.openapi()["paths"]

    expected = {
        "/api/v1/sessions",
        "/api/v1/sessions/{session_id}/generate-plan",
        "/api/v1/tasks/{task_id}/attempts",
        "/api/v1/tasks/{task_id}/skip",
        "/api/v1/journal/today/context",
        "/api/v1/journal/{local_date}/context",
        "/api/v1/journals/{journal_id}/revisions",
    }

    assert expected <= paths.keys()


def test_unimplemented_contract_returns_explicit_501() -> None:
    response = TestClient(app).get("/api/v1/home")

    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "service_not_implemented"
