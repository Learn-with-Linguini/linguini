"""Persistence and deterministic scoring for onboarding placement."""

from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.schemas.base import utc_now
from app.schemas.enums import ProficiencyLevel
from app.schemas.onboarding import (
    PlacementOption,
    PlacementQuestion,
    PlacementSubmission,
    PlacementTest,
)

metadata = MetaData()
placement_questions = Table(
    "onboarding_placement_questions", metadata,
    Column("id", Uuid, primary_key=True),
    Column("language_code", String(35), nullable=False),
    Column("question_key", String(80), nullable=False),
    Column("order_index", Integer, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("prompt_translation", Text, nullable=False),
    Column("skill", String(32), nullable=False),
    Column("difficulty", String(2), nullable=False),
    Column("options", JSONB, nullable=False),
    Column("correct_option", String(40), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
placement_attempts = Table(
    "onboarding_placement_attempts", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("user_id", Uuid, nullable=False),
    Column("language_code", String(35), nullable=False),
    Column("pathway", String(16), nullable=False),
    Column("answers", JSONB, nullable=False),
    Column("correct_count", Integer, nullable=False),
    Column("assigned_level", String(2), nullable=False),
    Column("scoring_version", String(40), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema="public",
)

SUPPORTED_LANGUAGES = {"fr", "es", "de", "ko"}


def placement_level(
    questions: list[PlacementQuestion], answers: dict[UUID, str], correct_options: dict[UUID, str]
) -> tuple[ProficiencyLevel, int]:
    """Score an adaptive path without requiring every question in the bank."""
    question_ids = {question.id for question in questions}
    answered_ids = set(answers)
    if len(answered_ids) != 3 or not answered_ids <= question_ids:
        raise ValueError("Complete the placement path before continuing.")
    correct_ids = {
        item for item in answered_ids if answers[item] == correct_options[item]
    }
    correct = len(correct_ids)
    difficulty = {question.id: question.difficulty for question in questions}
    a2_correct = sum(difficulty[item] == ProficiencyLevel.A2 for item in correct_ids)
    a1_correct = sum(difficulty[item] == ProficiencyLevel.A1 for item in correct_ids)
    level = ProficiencyLevel.A2 if a2_correct >= 2 else (
        ProficiencyLevel.A1 if a1_correct else ProficiencyLevel.A0
    )
    return level, correct


class OnboardingPlacementRepository:
    def __init__(self, engine: Engine, user_id: UUID) -> None:
        self.engine = engine
        self.user_id = user_id

    def test(self, language_code: str) -> PlacementTest:
        code = language_code.lower()
        if code not in SUPPORTED_LANGUAGES:
            raise ValueError("Placement is not available for this language.")
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(placement_questions).where(
                    placement_questions.c.language_code == code,
                    placement_questions.c.is_active.is_(True),
                ).order_by(placement_questions.c.order_index)
            ).mappings().all()
        return PlacementTest(language_code=code, questions=[
            PlacementQuestion(
                id=row["id"], question_key=row["question_key"],
                order_index=row["order_index"], prompt=row["prompt"],
                prompt_translation=row["prompt_translation"],
                skill=row["skill"], difficulty=row["difficulty"],
                options=[PlacementOption.model_validate(option) for option in row["options"]],
            ) for row in rows
        ])

    def submit(self, submission: PlacementSubmission) -> ProficiencyLevel:
        code = submission.language_code.lower()
        test = self.test(code)
        if submission.pathway == "beginner":
            level, correct = ProficiencyLevel.A0, 0
        else:
            question_ids = {question.id for question in test.questions}
            with self.engine.connect() as connection:
                keys = dict(connection.execute(
                    select(placement_questions.c.id, placement_questions.c.correct_option)
                    .where(placement_questions.c.id.in_(question_ids))
                ).all())
            level, correct = placement_level(test.questions, submission.answers, keys)
        now = utc_now()
        with self.engine.begin() as connection:
            connection.execute(insert(placement_attempts).values(
                user_id=self.user_id, language_code=code, pathway=submission.pathway,
                answers={str(key): value for key, value in submission.answers.items()},
                correct_count=correct, assigned_level=level.value,
                scoring_version="placement-v1", completed_at=now,
                created_at=now, updated_at=now,
            ))
        return level

    def check_answer(self, question_id: UUID, answer: str) -> tuple[bool, str]:
        with self.engine.connect() as connection:
            correct = connection.execute(
                select(placement_questions.c.correct_option).where(
                    placement_questions.c.id == question_id,
                    placement_questions.c.is_active.is_(True),
                )
            ).scalar_one_or_none()
        if correct is None:
            raise ValueError("Placement question not found.")
        return answer == correct, correct
