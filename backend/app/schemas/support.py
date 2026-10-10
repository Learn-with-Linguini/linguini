"""Schemas for learner support requests."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas.base import ApiModel

IssueType = Literal["general", "technical", "content", "account"]
LessonReportIssue = Literal[
    "answer_marked_incorrectly",
    "solution_incorrect",
    "wording_unclear",
    "audio_incorrect",
    "other",
]
AttachmentMimeType = Literal[
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "text/plain",
]


class SupportAttachmentRequest(ApiModel):
    file_name: Annotated[str, Field(min_length=1, max_length=120)]
    mime_type: AttachmentMimeType
    data_base64: Annotated[str, Field(min_length=1, max_length=7_100_000)]

    @field_validator("file_name")
    @classmethod
    def file_name_must_be_safe(cls, value: str) -> str:
        name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not name or name in {".", ".."}:
            raise ValueError("fileName must contain a valid file name")
        return name


class CreateSupportRequest(ApiModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    subject: Annotated[str, Field(min_length=3, max_length=160)]
    description: Annotated[str, Field(min_length=10, max_length=4_000)]
    issue_type: IssueType
    attachments: list[SupportAttachmentRequest] = Field(default_factory=list, max_length=3)

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("email must be a valid email address")
        return value

    @field_validator("subject")
    @classmethod
    def subject_must_not_contain_newlines(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("subject must be a single line")
        return value


class LessonReportContextField(ApiModel):
    label: Annotated[str, Field(min_length=1, max_length=80)]
    value: Annotated[str, Field(min_length=1, max_length=2_000)]


class CreateLessonReportRequest(ApiModel):
    report_type: Annotated[str, Field(min_length=3, max_length=120)]
    issue: LessonReportIssue
    additional_details: Annotated[str, Field(max_length=2_000)] = ""
    context: list[LessonReportContextField] = Field(default_factory=list, max_length=16)

    @field_validator("report_type")
    @classmethod
    def report_type_must_not_contain_newlines(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("reportType must be a single line")
        return value

class SupportRequestResponse(ApiModel):
    status: Literal["sent"] = "sent"
