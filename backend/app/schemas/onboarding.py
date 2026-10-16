"""Contracts for the short, image-led onboarding placement activity."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel, LanguageCode, NonEmptyText
from app.schemas.enums import ProficiencyLevel


class PlacementOption(ApiModel):
    value: NonEmptyText
    label: NonEmptyText


class PlacementQuestion(ApiModel):
    id: UUID
    question_key: NonEmptyText
    order_index: int
    prompt: NonEmptyText
    prompt_translation: NonEmptyText
    skill: NonEmptyText
    difficulty: ProficiencyLevel
    options: list[PlacementOption]


class PlacementTest(ApiModel):
    language_code: LanguageCode
    image_path: str = "/onboarding/placement-cafe-v1.png"
    questions: list[PlacementQuestion]


class PlacementSubmission(ApiModel):
    language_code: LanguageCode
    pathway: Literal["beginner", "placement"]
    answers: dict[UUID, Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        default_factory=dict
    )


class PlacementResult(ApiModel):
    proficiency_level: ProficiencyLevel
    message: str


class PlacementAnswerCheck(ApiModel):
    question_id: UUID
    answer: Annotated[str, Field(min_length=1, max_length=40)]


class PlacementAnswerFeedback(ApiModel):
    correct: bool
    correct_option: str
