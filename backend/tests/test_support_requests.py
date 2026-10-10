import asyncio
import base64
from email.message import EmailMessage
from uuid import UUID

import pytest

from app.api.routes.support import (
    create_lesson_report,
    create_public_support_request,
    create_support_request,
    decode_attachments,
)
from app.schemas.support import (
    CreateLessonReportRequest,
    CreatePublicSupportRequest,
    CreateSupportRequest,
    LessonReportContextField,
    SupportAttachmentRequest,
)
from app.services.support_mail import (
    SmtpSupportMailer,
    SupportAttachment,
    SupportMailSettings,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakeMailer:
    def __init__(self) -> None:
        self.sent: dict[str, object] | None = None

    def send(self, **kwargs: object) -> None:
        self.sent = kwargs


class FakeUsers:
    def __init__(self, email: str | None = "account@example.com") -> None:
        self.user_id = USER_ID
        self.email = email

    def get_current_user(self) -> object:
        return type("FakeUser", (), {"email": self.email})()


def support_request(**overrides: object) -> CreateSupportRequest:
    values: dict[str, object] = {
        "subject": "A translation looks wrong",
        "description": "The displayed answer does not match the photograph.",
        "issue_type": "content",
        "attachments": [],
    }
    values.update(overrides)
    return CreateSupportRequest(**values)


def test_support_request_decodes_allowed_attachment() -> None:
    request = support_request(
        attachments=[
            SupportAttachmentRequest(
                file_name="screenshot.png",
                mime_type="image/png",
                data_base64=base64.b64encode(b"png-data").decode(),
            )
        ]
    )

    attachments = decode_attachments(request)

    assert attachments == [
        SupportAttachment("screenshot.png", "image/png", b"png-data")
    ]


def test_support_route_passes_reply_address_and_context_to_mailer() -> None:
    mailer = FakeMailer()
    request = support_request()

    response = asyncio.run(create_support_request(request, FakeUsers(), mailer))

    assert response.status == "sent"
    assert mailer.sent is not None
    assert mailer.sent["learner_email"] == "account@example.com"
    assert mailer.sent["user_id"] == USER_ID
    assert mailer.sent["issue_type"] == "content"


def test_public_support_route_uses_visitor_email_without_a_user_id() -> None:
    mailer = FakeMailer()
    request = CreatePublicSupportRequest(
        email="visitor@example.com",
        subject="I have a question",
        description="I would like to know more about Linguini.",
        issue_type="general",
        attachments=[],
    )

    response = asyncio.run(create_public_support_request(request, mailer))

    assert response.status == "sent"
    assert mailer.sent is not None
    assert mailer.sent["learner_email"] == "visitor@example.com"
    assert mailer.sent["user_id"] is None


def test_lesson_report_uses_database_account_email() -> None:
    mailer = FakeMailer()
    request = CreateLessonReportRequest(
        report_type="Vocabulary answer",
        issue="solution_incorrect",
        additional_details="The photograph shows a different object.",
        context=[LessonReportContextField(label="Task ID", value="task-123")],
    )

    response = asyncio.run(create_lesson_report(request, FakeUsers(), mailer))

    assert response.status == "sent"
    assert mailer.sent is not None
    assert mailer.sent["learner_email"] == "account@example.com"
    assert mailer.sent["issue_type"] == "lesson report"
    assert "The displayed solution is incorrect" in str(mailer.sent["description"])
    assert "Task ID: task-123" in str(mailer.sent["description"])


def test_smtp_mailer_uses_support_recipient_and_learner_reply_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[EmailMessage] = []

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("smtp.gmail.com", 587, 15)

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def ehlo(self) -> None:
            return None

        def starttls(self, *, context: object) -> None:
            assert context is not None

        def login(self, username: str, password: str) -> None:
            assert (username, password) == ("sender@gmail.com", "app-password")

        def send_message(self, message: EmailMessage) -> None:
            captured.append(message)

    monkeypatch.setattr("app.services.support_mail.smtplib.SMTP", FakeSmtp)
    mailer = SmtpSupportMailer(
        SupportMailSettings(
            host="smtp.gmail.com",
            port=587,
            username="sender@gmail.com",
            password="app-password",
            from_email="sender@gmail.com",
            to_email="linguini-support@googlegroups.com",
        )
    )

    mailer.send(
        user_id=USER_ID,
        learner_email="learner@example.com",
        issue_type="technical",
        subject="Upload failed",
        description="The upload stopped after I selected a photo.",
        attachments=[],
    )

    assert len(captured) == 1
    message = captured[0]
    assert message["To"] == "linguini-support@googlegroups.com"
    assert message["Reply-To"] == "learner@example.com"
    assert message["From"] == "Linguini Support <sender@gmail.com>"
    assert message["Subject"] == "[Linguini technical] Upload failed"


def test_smtp_lesson_report_includes_account_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[EmailMessage] = []

    class FakeSmtp:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def ehlo(self) -> None:
            return None

        def starttls(self, *, context: object) -> None:
            assert context is not None

        def login(self, _username: str, _password: str) -> None:
            return None

        def send_message(self, message: EmailMessage) -> None:
            captured.append(message)

    monkeypatch.setattr("app.services.support_mail.smtplib.SMTP", FakeSmtp)
    mailer = SmtpSupportMailer(
        SupportMailSettings(
            host="smtp.gmail.com",
            port=587,
            username="linguini.feedback@gmail.com",
            password="app-password",
            from_email="linguini.feedback@gmail.com",
            to_email="linguini-support@googlegroups.com",
        )
    )

    mailer.send(
        user_id=USER_ID,
        learner_email="account@example.com",
        issue_type="lesson report",
        subject="Grammar answer",
        description="Selected issue: The displayed solution is incorrect",
        attachments=[],
    )

    assert len(captured) == 1
    assert captured[0]["Reply-To"] == "account@example.com"
    assert "Learner email: account@example.com" in captured[0].get_content()
