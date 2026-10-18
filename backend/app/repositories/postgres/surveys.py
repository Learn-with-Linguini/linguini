"""Survey persistence against PostgreSQL table managed by Prisma migrations."""

from datetime import UTC, datetime
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
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.surveys import CreateSurveyRequest, SurveyResponse

user_surveys = Table(
    "user_surveys",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid),
    Column("email", String(320)),
    Column("rating", Integer, nullable=False),
    Column("usage_frequency", Text, nullable=False),
    Column("motivation", Text, nullable=False),
    Column("improvements", Text, nullable=False),
    Column("receive_follow_up", Boolean, nullable=False),
    Column("trigger_source", String(32), nullable=False),
    Column("lesson_count", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class PostgresSurveyRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(
        self,
        *,
        user_id: UUID | None,
        email: str | None,
        request: CreateSurveyRequest,
    ) -> SurveyResponse:
        survey_id = uuid4()
        created_at = datetime.now(UTC)
        values = {
            "id": survey_id,
            "user_id": user_id,
            "email": email,
            "rating": request.rating,
            "usage_frequency": request.usage_frequency.strip(),
            "motivation": request.motivation.strip(),
            "improvements": request.improvements.strip(),
            "receive_follow_up": request.receive_follow_up,
            "trigger_source": request.trigger_source.strip() or "profile",
            "lesson_count": request.lesson_count,
            "created_at": created_at,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(user_surveys).values(**values))
            return SurveyResponse(**values)
        except SQLAlchemyError as exc:
            raise RuntimeError("Unable to save survey response.") from exc
