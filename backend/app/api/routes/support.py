"""Authenticated learner support submission endpoint."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import get_current_user_id
from app.schemas.support import (
    CreateLessonReportRequest,
    CreateSupportRequest,
    SupportRequestResponse,
)
from app.services.support_mail import (
    SmtpSupportMailer,
    SupportAttachment,
    SupportMailConfigurationError,
    SupportMailDeliveryError,
    load_support_mail_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/support", tags=["support"])

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024

LESSON_ISSUE_LABELS = {
    "answer_marked_incorrectly": "My answer was marked incorrectly",
    "solution_incorrect": "The displayed solution is incorrect",
    "wording_unclear": "The wording or translation is unclear",
    "audio_incorrect": "The audio or pronunciation is incorrect",
    "other": "Something else",
}


def get_support_mailer() -> SmtpSupportMailer:
    return SmtpSupportMailer(load_support_mail_settings())


def decode_attachments(request: CreateSupportRequest) -> list[SupportAttachment]:
    decoded: list[SupportAttachment] = []
    total_bytes = 0
    for attachment in request.attachments:
        try:
            content = base64.b64decode(attachment.data_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_attachment", "message": "An attachment is invalid."},
            ) from exc
        if not content or len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "attachment_too_large",
                    "message": "Each attachment must be 5 MB or smaller.",
                },
            )
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "attachments_too_large",
                    "message": "Attachments must total 10 MB or less.",
                },
            )
        decoded.append(
            SupportAttachment(
                file_name=attachment.file_name,
                mime_type=attachment.mime_type,
                content=content,
            )
        )
    return decoded


@router.post(
    "/requests",
    response_model=SupportRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_support_request(
    request: CreateSupportRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    mailer: Annotated[SmtpSupportMailer, Depends(get_support_mailer)],
) -> SupportRequestResponse:
    attachments = decode_attachments(request)
    try:
        await asyncio.to_thread(
            mailer.send,
            user_id=user_id,
            learner_email=request.email,
            issue_type=request.issue_type,
            subject=request.subject,
            description=request.description,
            attachments=attachments,
        )
    except SupportMailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "support_unavailable",
                "message": "Support submissions are being set up. Please try again later.",
            },
        ) from exc
    except SupportMailDeliveryError as exc:
        logger.warning("Support email delivery failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "support_delivery_failed",
                "message": "We could not send your request. Please try again.",
            },
        ) from exc
    return SupportRequestResponse()


@router.post(
    "/lesson-reports",
    response_model=SupportRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lesson_report(
    request: CreateLessonReportRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    mailer: Annotated[SmtpSupportMailer, Depends(get_support_mailer)],
) -> SupportRequestResponse:
    context = "\n".join(f"{field.label}: {field.value}" for field in request.context)
    description_parts = [f"Selected issue: {LESSON_ISSUE_LABELS[request.issue]}"]
    if request.additional_details.strip():
        description_parts.extend(("", "Additional details:", request.additional_details.strip()))
    if context:
        description_parts.extend(("", "Exercise context:", context))
    try:
        await asyncio.to_thread(
            mailer.send,
            user_id=user_id,
            learner_email=None,
            issue_type="lesson report",
            subject=request.report_type,
            description="\n".join(description_parts),
            attachments=[],
        )
    except SupportMailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "support_unavailable",
                "message": "Lesson reporting is being set up. Please try again later.",
            },
        ) from exc
    except SupportMailDeliveryError as exc:
        logger.warning("Lesson report email delivery failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "support_delivery_failed",
                "message": "We could not send your report. Please try again.",
            },
        ) from exc
    return SupportRequestResponse()
