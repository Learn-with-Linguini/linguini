"""Requests are bounded before JSON parsing, mail delivery or database writes."""

import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_auth_settings, get_authenticated_identity
from app.api.dependencies import get_survey_repository, get_user_repository
from app.api.request_security import RequestSecurityMiddleware, SubmissionLimiter
from app.api.routes.support import get_support_mailer
from app.main import create_app
from app.schemas.surveys import SurveyResponse
from app.services.auth import AuthSettings


def asgi_request(chunks, *, headers=(), path="/api/v1/test", middleware_options=None):
    """Send raw ASGI chunks, including lengths a normal HTTP client would fix."""
    reached = []
    sent = []
    received = []
    source = iter(chunks)

    async def receive():
        message = next(source, {"type": "http.disconnect"})
        received.append(message)
        return message

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        reached.append(body)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {
        "type": "http", "method": "POST", "path": path,
        "headers": headers, "client": ("198.51.100.1", 5000),
    }
    middleware = RequestSecurityMiddleware(app, **(middleware_options or {}))
    asyncio.run(middleware(scope, receive, send))
    return reached, sent, received


def chunk(body, *, more=False):
    return {"type": "http.request", "body": body, "more_body": more}


@pytest.mark.parametrize("headers", [(), [(b"content-length", b"1")]])
def test_oversized_chunks_never_reach_json_parser(headers):
    reached, sent, received = asgi_request(
        [chunk(b"private-", more=True), chunk(b"data", more=True), chunk(b"ignored")],
        headers=headers, middleware_options={"max_request_bytes": 8},
    )
    assert reached == []
    assert sent[0]["status"] == 413
    assert len(received) == 2
    assert b"private" not in sent[1]["body"]


def test_declared_oversize_is_rejected_without_reading_body():
    reached, sent, received = asgi_request(
        [chunk(b"large")], headers=[(b"content-length", b"999999999999999999999999999")],
    )
    assert reached == []
    assert received == []
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("headers", [
    [(b"content-length", b"-1")],
    [(b"content-length", b"abc")],
    [(b"content-length", b"1"), (b"content-length", b"1")],
])
def test_malformed_lengths_never_reach_handler(headers):
    reached, sent, received = asgi_request([chunk(b"x")], headers=headers)
    assert reached == []
    assert received == []
    assert sent[0]["status"] == 400


def test_body_at_limit_is_replayed_without_changing_content():
    reached, sent, _ = asgi_request(
        [chunk(b"abc", more=True), chunk(b"def")],
        middleware_options={"max_request_bytes": 6},
    )
    assert reached == [b"abcdef"]
    assert sent[0]["status"] == 200


def test_support_attachment_allowance_does_not_expand_other_request_limits():
    options = {"max_request_bytes": 3, "max_support_bytes": 10}
    reached, sent, _ = asgi_request(
        [chunk(b"123456")], path="/api/v1/support/requests", middleware_options=options,
    )
    assert reached == [b"123456"]
    assert sent[0]["status"] == 200
    reached, sent, _ = asgi_request(
        [chunk(b"123456")], path="/api/v1/support/lesson-reports", middleware_options=options,
    )
    assert reached == []
    assert sent[0]["status"] == 413


def test_disconnected_request_never_invokes_handler():
    reached, sent, _ = asgi_request([chunk(b"x", more=True), {"type": "http.disconnect"}])
    assert reached == []
    assert sent == []


def test_limiter_expiry_capacity_and_client_isolation():
    now = [100.0]
    limiter = SubmissionLimiter(max_entries=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.retry_after("support", "first", 1) is None
    assert limiter.retry_after("support", "first", 1) == 10
    assert limiter.retry_after("support", "second", 1) is None
    # A full table must not evict the first client and reset its allowance.
    assert limiter.retry_after("support", "third", 1) == 10
    assert limiter.retry_after("support", "first", 1) == 10
    now[0] += 9.5
    assert limiter.retry_after("support", "first", 1) == 1
    now[0] += 0.5
    assert limiter.retry_after("support", "third", 1) is None
    assert limiter.retry_after("support", "first", 1) is None


def test_concurrent_submissions_cannot_exceed_allowance():
    limiter = SubmissionLimiter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: limiter.retry_after("support", "client", 5), range(50)))
    assert results.count(None) == 5


def public_support_payload():
    return {
        "email": "visitor@example.com", "subject": "A question about lessons",
        "description": "Please help me understand the practice feature.", "issueType": "general",
    }


def test_public_support_rate_limit_stops_mail_and_ignores_spoofed_forwarded_headers():
    app = create_app()
    deliveries = []

    class Mailer:
        def send(self, **kwargs):
            deliveries.append(kwargs)

    app.dependency_overrides[get_support_mailer] = Mailer
    client = TestClient(app)
    for index in range(5):
        response = client.post(
            "/api/v1/support/public-requests", json=public_support_payload(),
            headers={"X-Forwarded-For": f"198.51.100.{index}"},
        )
        assert response.status_code == 201
    response = client.post(
        "/api/v1/support/public-requests", json=public_support_payload(),
        headers={"X-Forwarded-For": "203.0.113.1", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 600
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert len(deliveries) == 5
    # The guard runs before JSON parsing, so even a malformed retry is throttled.
    assert client.post(
        "/api/v1/support/public-requests", content=b"{invalid-json",
        headers={"Content-Type": "application/json"},
    ).status_code == 429


def test_support_accepts_valid_attachments_larger_than_the_normal_json_limit():
    app = create_app()
    deliveries = []

    class Mailer:
        def send(self, **kwargs):
            deliveries.append(kwargs)

    app.dependency_overrides[get_support_mailer] = Mailer
    attachment = b"x" * (1024 * 1024)
    response = TestClient(app).post("/api/v1/support/public-requests", json={
        **public_support_payload(),
        "attachments": [{
            "fileName": "details.txt", "mimeType": "text/plain",
            "dataBase64": base64.b64encode(attachment).decode(),
        }],
    })
    assert response.status_code == 201
    assert deliveries[0]["attachments"][0].content == attachment


def test_public_survey_rate_limit_stops_database_writes():
    app = create_app()
    writes = []

    class Surveys:
        def create(self, *, user_id, email, request):
            writes.append(request)
            return SurveyResponse(
                id=uuid4(), user_id=user_id, email=email,
                created_at=datetime.now(UTC), **request.model_dump(exclude={"email"}),
            )

    app.dependency_overrides[get_survey_repository] = Surveys
    app.dependency_overrides[get_user_repository] = lambda: None
    app.dependency_overrides[get_authenticated_identity] = lambda: None
    app.dependency_overrides[get_auth_settings] = lambda: AuthSettings(
        mode="supabase", supabase_url="https://example.supabase.co", audience="authenticated",
        jwt_secret=None, allow_anonymous=False,
    )
    client = TestClient(app)
    for _ in range(10):
        assert client.post("/api/v1/surveys", json={"rating": 5}).status_code == 201
    response = client.post("/api/v1/surveys", json={"rating": 5})
    assert response.status_code == 429
    assert len(writes) == 10


def test_body_limit_keeps_cors_and_preflights_working():
    client = TestClient(create_app())
    headers = {"Origin": "http://localhost:5173"}
    response = client.post("/api/v1/surveys", content=b"x" * (1024 * 1024 + 1), headers=headers)
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert json.loads(response.content)["detail"]["code"] == "request_too_large"
    response = client.options("/api/v1/surveys", headers={
        **headers, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
