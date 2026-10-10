"""SMTP delivery for learner support requests."""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID


class SupportMailConfigurationError(RuntimeError):
    """Raised when support email delivery is not configured."""


class SupportMailDeliveryError(RuntimeError):
    """Raised when the SMTP provider rejects or cannot deliver a message."""


@dataclass(frozen=True)
class SupportMailSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    to_email: str
    from_name: str = "Linguini Support"
    use_tls: bool = True

    @property
    def configured(self) -> bool:
        return all(
            (self.host, self.username, self.password, self.from_email, self.to_email)
        )


@dataclass(frozen=True)
class SupportAttachment:
    file_name: str
    mime_type: str
    content: bytes


def load_support_mail_settings() -> SupportMailSettings:
    return SupportMailSettings(
        host=os.getenv("SUPPORT_SMTP_HOST", "smtp.gmail.com").strip(),
        port=int(os.getenv("SUPPORT_SMTP_PORT", "587")),
        username=os.getenv("SUPPORT_SMTP_USERNAME", "").strip(),
        password=os.getenv("SUPPORT_SMTP_PASSWORD", "").strip(),
        from_email=os.getenv("SUPPORT_FROM_EMAIL", "").strip(),
        to_email=os.getenv(
            "SUPPORT_TO_EMAIL", "linguini-support@googlegroups.com"
        ).strip(),
        from_name=os.getenv("SUPPORT_FROM_NAME", "Linguini Support").strip(),
        use_tls=os.getenv("SUPPORT_SMTP_USE_TLS", "true").strip().lower() == "true",
    )


class SmtpSupportMailer:
    def __init__(self, settings: SupportMailSettings) -> None:
        self.settings = settings

    def send(
        self,
        *,
        user_id: UUID,
        learner_email: str | None,
        issue_type: str,
        subject: str,
        description: str,
        attachments: list[SupportAttachment],
    ) -> None:
        if not self.settings.configured:
            raise SupportMailConfigurationError("Support email delivery is not configured.")

        message = EmailMessage()
        message["From"] = formataddr((self.settings.from_name, self.settings.from_email))
        message["To"] = self.settings.to_email
        if learner_email:
            message["Reply-To"] = learner_email
        message["Subject"] = f"[Linguini {issue_type}] {subject}"
        learner_line = (
            f"Learner email: {learner_email}"
            if learner_email
            else "Learner email: not collected"
        )
        message.set_content(
            "\n".join(
                (
                    f"Issue type: {issue_type}",
                    learner_line,
                    f"Authenticated user ID: {user_id}",
                    "",
                    "Description:",
                    description,
                )
            )
        )

        for attachment in attachments:
            maintype, subtype = attachment.mime_type.split("/", 1)
            message.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.file_name,
            )

        try:
            with smtplib.SMTP(
                self.settings.host, self.settings.port, timeout=15
            ) as smtp:
                smtp.ehlo()
                if self.settings.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(self.settings.username, self.settings.password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise SupportMailDeliveryError("Support email could not be delivered.") from exc
