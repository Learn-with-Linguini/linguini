"""Daily rankings derived from accepted Basil credits in the account ledger."""

from datetime import timedelta

from sqlalchemy import Date, cast, func, select

from app.repositories.postgres.game_resources import game_resource_events
from app.repositories.postgres.gamification import basil_totals
from app.repositories.postgres.users import users
from app.schemas.leaderboard import ChefLeaderboardEntry, ChefLeaderboardResponse


def leaderboard_snapshot(connection, user_id):
    """Caller locks its account; all learners with Basil join automatically."""
    totals = basil_totals(connection, user_id)
    start = totals.day_ends_at - timedelta(days=1)
    earned = game_resource_events.c.kind == "basilEarned"
    scores = (
        select(
            users.c.id.label("user_id"), users.c.display_name, users.c.avatar,
            func.sum(game_resource_events.c.basil_delta).label("basil"),
        )
        .join(game_resource_events, game_resource_events.c.user_id == users.c.id)
        .where(
            earned,
            game_resource_events.c.created_at >= start,
            game_resource_events.c.created_at < totals.day_ends_at,
        )
        .group_by(users.c.id, users.c.display_name, users.c.avatar)
        .having(func.sum(game_resource_events.c.basil_delta) > 0)
        .cte("daily_chef_scores")
    )
    ranked = select(
        scores, func.rank().over(order_by=scores.c.basil.desc()).label("rank"),
    ).cte("daily_chef_ranks")
    top = connection.execute(
        select(ranked).order_by(ranked.c.basil.desc(), ranked.c.user_id).limit(10),
    ).mappings().all()
    mine = connection.execute(
        select(ranked.c.rank).where(ranked.c.user_id == user_id),
    ).scalar_one_or_none()
    next_score = connection.execute(
        select(func.min(scores.c.basil)).where(scores.c.basil > totals.today),
    ).scalar_one() if mine is not None else None
    days = select(func.sum(game_resource_events.c.basil_delta).label("basil")).where(
        game_resource_events.c.user_id == user_id, earned,
    ).group_by(cast(func.timezone("UTC", game_resource_events.c.created_at), Date)).subquery()
    personal_best = connection.execute(
        select(func.coalesce(func.max(days.c.basil), 0)),
    ).scalar_one()
    return ChefLeaderboardResponse(
        competition_day=totals.competition_day,
        day_ends_at=totals.day_ends_at,
        today_basil=totals.today,
        personal_best=personal_best,
        current_rank=mine,
        basil_to_next_rank=next_score - totals.today + 1 if next_score is not None else None,
        top=[ChefLeaderboardEntry(
            rank=row["rank"], display_name=row["display_name"].strip() or "Learner",
            basil=row["basil"],
            avatar=row["avatar"],
        ) for row in top],
    )
