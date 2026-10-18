"""Tests for learner satisfaction and feedback survey submissions."""

from uuid import UUID

from fastapi import status
from fastapi.testclient import TestClient

from app.api.auth import get_authenticated_identity, get_current_user_id
from app.api.dependencies import get_survey_repository, get_user_repository
from app.main import app
from app.schemas.surveys import CreateSurveyRequest, SurveyResponse
from app.services.auth import AuthenticatedIdentity

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "learner@example.com"


class FakeSurveyRepo:
    def __init__(self) -> None:
        self.surveys: list[dict] = []

    def create(self, *, user_id, email, request: CreateSurveyRequest) -> SurveyResponse:
        from datetime import UTC, datetime
        from uuid import uuid4

        record = {
            "id": uuid4(),
            "user_id": user_id,
            "email": email,
            "rating": request.rating,
            "usage_frequency": request.usage_frequency,
            "motivation": request.motivation,
            "improvements": request.improvements,
            "receive_follow_up": request.receive_follow_up,
            "trigger_source": request.trigger_source,
            "lesson_count": request.lesson_count,
            "created_at": datetime.now(UTC),
        }
        self.surveys.append(record)
        return SurveyResponse(**record)


class FakeUserRepo:
    def get_by_id(self, user_id):
        return type("FakeUser", (), {"id": user_id, "email": USER_EMAIL})()


def test_submit_survey_success():
    fake_repo = FakeSurveyRepo()
    fake_user_repo = FakeUserRepo()

    app.dependency_overrides[get_survey_repository] = lambda: fake_repo
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    app.dependency_overrides[get_authenticated_identity] = lambda: AuthenticatedIdentity(
        subject="test-subject", email=USER_EMAIL, is_anonymous=False
    )

    try:
        client = TestClient(app)
        payload = {
            "rating": 5,
            "usage_frequency": "Every morning during my commute",
            "motivation": "Preparing for a trip to France",
            "improvements": "More street scene photos",
            "receive_follow_up": True,
            "trigger_source": "lesson_completed",
            "lesson_count": 6,
        }
        response = client.post("/api/v1/surveys", json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["rating"] == 5
        assert data["usageFrequency"] == payload["usage_frequency"]
        assert data["motivation"] == payload["motivation"]
        assert data["improvements"] == payload["improvements"]
        assert data["receiveFollowUp"] is True
        assert data["triggerSource"] == "lesson_completed"
        assert data["lessonCount"] == 6

        # Check repository record
        assert len(fake_repo.surveys) == 1
        saved = fake_repo.surveys[0]
        assert saved["user_id"] == USER_ID
        assert saved["email"] == USER_EMAIL
        assert saved["rating"] == 5

        # Can submit multiple times from profile
        response2 = client.post("/api/v1/surveys", json={
            "rating": 4,
            "usage_frequency": "Daily",
            "motivation": "Fun",
            "improvements": "Audio speed control",
            "receive_follow_up": False,
            "trigger_source": "profile",
        })
        assert response2.status_code == status.HTTP_201_CREATED
        assert len(fake_repo.surveys) == 2
    finally:
        app.dependency_overrides.clear()


def test_submit_survey_invalid_rating():
    fake_repo = FakeSurveyRepo()
    fake_user_repo = FakeUserRepo()

    app.dependency_overrides[get_survey_repository] = lambda: fake_repo
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    app.dependency_overrides[get_authenticated_identity] = lambda: None

    try:
        client = TestClient(app)
        # Rating 0 is invalid (must be 1-5)
        response = client.post("/api/v1/surveys", json={"rating": 0})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Rating 6 is invalid
        response2 = client.post("/api/v1/surveys", json={"rating": 6})
        assert response2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    finally:
        app.dependency_overrides.clear()
