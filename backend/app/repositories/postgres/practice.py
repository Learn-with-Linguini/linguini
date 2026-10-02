"""Session table definitions and progress derived from normalized encounters."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB

from app.schemas.enums import SessionFailureCode, SessionStatus
from app.schemas.progress import StoredProgress

sessions = Table(
    "sessions",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid, nullable=False),
    Column("scene_media_asset_id", Uuid, nullable=False),
    Column(
        "session_status",
        ENUM(
            SessionStatus,
            name="session_status",
            schema="public",
            values_callable=lambda statuses: [status.value for status in statuses],
            create_type=False,
        ),
        key="status",
        nullable=False,
    ),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("abandoned_at", DateTime(timezone=True)),
    Column("analysis_draft", JSONB(none_as_null=True)),
    Column("session_title", String),
    Column("session_summary", String),
    Column(
        "failure_code",
        ENUM(
            SessionFailureCode,
            name="session_failure_code",
            schema="public",
            values_callable=lambda codes: [code.value for code in codes],
            create_type=False,
        ),
    ),
    Column("idempotency_key", String(200)),
    schema="public",
)


class SessionBackedLearningRepository:
    def __init__(self, engine, user_id, vocabulary):
        self.engine = engine
        self.user_id = user_id
        self.vocabulary = vocabulary

    def get_progress(self, user_id, language_code=None, timezone="UTC"):
        from app.repositories.postgres.language_profiles import language_profiles
        from app.repositories.postgres.scenes import preloaded_scenes
        from app.repositories.postgres.tasks import session_tasks
        from app.repositories.postgres.xp import xp_events
        from app.schemas.progress import ScenarioProgress, Streak, StreakDay

        if user_id != self.user_id:
            return None
        with self.engine.connect() as connection:
            activity_query = select(xp_events.c.amount, xp_events.c.occurred_at).where(
                xp_events.c.user_id == user_id
            )
            if language_code:
                activity_query = activity_query.join(
                    language_profiles,
                    language_profiles.c.id == xp_events.c.language_profile_id,
                ).where(
                    func.lower(language_profiles.c.target_language_code) == language_code.lower()
                )
            activity_rows = connection.execute(activity_query).all()
            xp = sum(row.amount for row in activity_rows)
            learner_timezone = ZoneInfo(timezone)
            today = datetime.now(learner_timezone).date()
            streak_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
            active_dates = {
                local_date
                for _, occurred_at in activity_rows
                if (local_date := occurred_at.astimezone(learner_timezone).date()) <= today
            }
            current_streak = 0
            for day in reversed(streak_dates):
                if day not in active_dates:
                    break
                current_streak += 1
            streak = Streak(
                current=current_streak,
                days=[StreakDay(date=day, active=day in active_dates) for day in streak_dates],
            )
            query = (
                select(sessions, preloaded_scenes.c.slug, preloaded_scenes.c.title)
                .join(language_profiles, language_profiles.c.id == sessions.c.language_profile_id)
                .outerjoin(
                    preloaded_scenes,
                    preloaded_scenes.c.media_asset_id == sessions.c.scene_media_asset_id,
                )
                .where(
                    sessions.c.user_id == user_id,
                    sessions.c.status.in_(["inProgress", "completed"]),
                )
                .order_by(sessions.c.started_at)
            )
            if language_code:
                query = query.where(
                    func.lower(language_profiles.c.target_language_code) == language_code.lower()
                )
            scenarios = {}
            for row in connection.execute(query).mappings():
                states = (
                    connection.execute(
                        select(session_tasks.c.status).where(
                            session_tasks.c.session_id == row["id"]
                        )
                    )
                    .scalars()
                    .all()
                )
                if not states:
                    continue
                scene_id = row["slug"] or str(row["id"])
                scenarios[scene_id] = ScenarioProgress(
                    scene_id=scene_id,
                    session_id=row["id"],
                    media_asset_id=row["scene_media_asset_id"],
                    title=row["title"] or "Your uploaded photo",
                    status="completed" if row["status"] == "completed" else "in-progress",
                    completed_task_count=states.count("completed"),
                    total_task_count=len(states),
                    level="Starter",
                )
            return StoredProgress(
                user_id=user_id,
                language_code=language_code or "es",
                xp=xp,
                scenarios=list(scenarios.values()),
                leaderboard=[],
                streak=streak,
            )

    def list_vocabulary(self, user_id):
        return self.vocabulary.list_vocabulary(user_id)
