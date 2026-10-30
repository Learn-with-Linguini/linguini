"""Daily photo challenges: one scene per UTC day, word counts, and a rank bonus.

A challenge entry ties a normal lesson session to the day's scene. When that
session completes during the day, its confirmed object labels are recorded once
per learner. After the day ends, the first request settles it: learners are
ranked by how rarely others found their words and paid a flat Basil bonus.

Completion takes a shared advisory lock on the day and settlement an exclusive
one, so a completion either lands before the day is settled or is refused.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction
from uuid import UUID

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert

from app.repositories.postgres.game_resources import game_resource_events, reward_basil
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_objects
from app.repositories.practice import PracticeConflictError
from app.schemas.base import utc_now
from app.schemas.daily_challenges import (
    DailyChallengeResponse,
    DailyChallengeResult,
    DailyChallengeWord,
)

POLICY_VERSION = "daily-challenge.v1"
# Flat bonus by rarity rank; ties share a rank and its bonus.
RANK_BONUS = {1: 50, 2: 30, 3: 20}
TOP_TEN_BONUS = 10
FINISHER_BONUS = 5
# Learners may add their own objects, so a session counts at most this many words.
MAX_WORDS_PER_ENTRY = 20
WORDS_SHOWN = 30
SCENES = (
    ("cafe", "Café", "at the café"),
    ("kitchen", "Kitchen", "in the kitchen"),
    ("park", "Park", "in the park"),
    ("supermarket", "Supermarket", "at the supermarket"),
    ("desk", "Desk", "at your desk"),
    ("bedroom", "Bedroom", "in the bedroom"),
    ("street", "Street", "on the street"),
    ("bathroom", "Bathroom", "in the bathroom"),
    ("restaurant", "Restaurant", "at a restaurant"),
    ("garden", "Garden", "in the garden"),
    ("bus-stop", "Bus stop", "at the bus stop"),
    ("living-room", "Living room", "in the living room"),
    ("market", "Market", "at the market"),
    ("bakery", "Bakery", "at the bakery"),
    ("classroom", "Classroom", "in a classroom"),
    ("train-station", "Train station", "at the train station"),
    ("beach", "Beach", "at the beach"),
    ("gym", "Gym", "at the gym"),
)
SCENE_TITLES = {key: title for key, title, *_ in SCENES}
TERMINAL = {"completed", "abandoned", "failed"}

metadata = MetaData()
challenge_entries = Table(
    "daily_challenge_entries",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("challenge_day", Date, nullable=False),
    Column("scene_key", String(40), nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("session_id", Uuid, nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
challenge_finds = Table(
    "daily_challenge_finds",
    metadata,
    Column("challenge_day", Date, primary_key=True),
    Column("user_id", Uuid, primary_key=True),
    Column("label_key", Text, primary_key=True),
    Column("label", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
challenge_settlements = Table(
    "daily_challenge_settlements",
    metadata,
    Column("challenge_day", Date, primary_key=True),
    Column("participant_count", Integer, nullable=False),
    Column("policy_version", String(40), nullable=False),
    Column("settled_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


def challenge_day(now: datetime | None = None) -> date:
    return (now or utc_now()).astimezone(UTC).date()


def day_ends_at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)


def scene_for(day: date) -> tuple[str, str, str]:
    """(key, title, phrase) for the day's scene."""
    return SCENES[day.toordinal() % len(SCENES)]


def label_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _day_lock(c, day, *, shared):
    statement = (
        "SELECT pg_advisory_xact_lock_shared(hashtextextended(:key, 0))"
        if shared
        else "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
    )
    c.execute(
        text(statement),
        {"key": f"daily-challenge:{day.isoformat()}"},
    )


def _learner_lock(c, user_id, day):
    c.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"daily-challenge:{day.isoformat()}:{user_id}"},
    )


def _settled(c, day):
    return c.execute(
        select(challenge_settlements.c.challenge_day).where(
            challenge_settlements.c.challenge_day == day
        )
    ).first() is not None


def enter_challenge(c, user_id: UUID, session_id: UUID, day: date, media_source: str) -> None:
    """Tag a new or resumed lesson session as today's challenge entry."""
    if day != challenge_day():
        raise PracticeConflictError("That daily challenge has ended. Try today's scene.")
    if media_source not in {"camera", "userUpload"}:
        raise PracticeConflictError("Take your own photo for the daily challenge.")
    c.execute(
        insert(challenge_entries)
        .values(
            challenge_day=day,
            scene_key=scene_for(day)[0],
            user_id=user_id,
            session_id=session_id,
            created_at=utc_now(),
        )
        .on_conflict_do_nothing(index_elements=["session_id"])
    )


def record_completion(c, user_id: UUID, session_id: UUID) -> None:
    """Caller has just completed the session. Counts its words once per learner and day."""
    entry = c.execute(
        select(challenge_entries).where(
            challenge_entries.c.session_id == session_id,
            challenge_entries.c.user_id == user_id,
        )
    ).mappings().first()
    if entry is None or entry["completed_at"] is not None:
        return
    day = entry["challenge_day"]
    now = utc_now()
    if now >= day_ends_at(day):
        return
    _day_lock(c, day, shared=True)
    if _settled(c, day):
        return
    _learner_lock(c, user_id, day)
    already = c.execute(
        select(challenge_entries.c.id).where(
            challenge_entries.c.user_id == user_id,
            challenge_entries.c.challenge_day == day,
            challenge_entries.c.completed_at.is_not(None),
        )
    ).first()
    if already:
        return
    c.execute(
        update(challenge_entries)
        .where(challenge_entries.c.id == entry["id"])
        .values(completed_at=now)
    )
    labels = c.execute(
        select(scene_objects.c.label).where(scene_objects.c.session_id == session_id)
    ).scalars()
    words = {}
    for label in labels:
        key = label_key(label)
        if key and key not in words:
            words[key] = " ".join(label.split())
    rows = [
        dict(challenge_day=day, user_id=user_id, label_key=key, label=label, created_at=now)
        for key, label in list(words.items())[:MAX_WORDS_PER_ENTRY]
    ]
    if rows:
        c.execute(insert(challenge_finds).values(rows).on_conflict_do_nothing())


def rarity_ranks(finds: dict[UUID, set[str]]) -> dict[UUID, tuple[int, Fraction]]:
    """Each word scores participants / finders; learners rank by their total."""
    finders = defaultdict(int)
    for words in finds.values():
        for word in words:
            finders[word] += 1
    total = len(finds)
    scores = {
        user_id: sum((Fraction(total, finders[word]) for word in words), Fraction(0))
        for user_id, words in finds.items()
    }
    ordered = sorted(scores.values(), reverse=True)
    return {user_id: (ordered.index(score) + 1, score) for user_id, score in scores.items()}


def rank_bonus(rank: int) -> int:
    return RANK_BONUS.get(rank, TOP_TEN_BONUS if rank <= 10 else FINISHER_BONUS)


def _finds(c, day):
    finds = {
        row.user_id: set()
        for row in c.execute(
            select(challenge_entries.c.user_id).where(
                challenge_entries.c.challenge_day == day,
                challenge_entries.c.completed_at.is_not(None),
            )
        )
    }
    for row in c.execute(
        select(challenge_finds.c.user_id, challenge_finds.c.label_key).where(
            challenge_finds.c.challenge_day == day
        )
    ):
        finds.setdefault(row.user_id, set()).add(row.label_key)
    return finds


def settle_day(c, day: date) -> bool:
    """Pay one finished day's bonuses exactly once. Returns whether this call settled it."""
    if day >= challenge_day():
        return False
    _day_lock(c, day, shared=False)
    if _settled(c, day):
        return False
    finds = _finds(c, day)
    for user_id, (rank, score) in rarity_ranks(finds).items():
        reward_basil(
            c,
            user_id,
            f"daily-challenge:{day.isoformat()}",
            amount=rank_bonus(rank),
            payload={
                "challengeDay": day.isoformat(),
                "sceneKey": scene_for(day)[0],
                "rank": rank,
                "participants": len(finds),
                "rarity": float(score),
                "policyVersion": POLICY_VERSION,
            },
        )
    c.execute(
        insert(challenge_settlements)
        .values(
            challenge_day=day,
            participant_count=len(finds),
            policy_version=POLICY_VERSION,
            settled_at=utc_now(),
        )
        .on_conflict_do_nothing()
    )
    return True


def settle_finished_days(c) -> None:
    pending = c.execute(
        select(challenge_entries.c.challenge_day)
        .where(
            challenge_entries.c.challenge_day < challenge_day(),
            challenge_entries.c.completed_at.is_not(None),
            challenge_entries.c.challenge_day.not_in(
                select(challenge_settlements.c.challenge_day)
            ),
        )
        .distinct()
        .order_by(challenge_entries.c.challenge_day)
    ).scalars().all()
    for day in pending:
        settle_day(c, day)


def _last_result(c, user_id, today):
    row = c.execute(
        select(game_resource_events.c.basil_delta, game_resource_events.c.payload)
        .where(
            game_resource_events.c.user_id == user_id,
            game_resource_events.c.source_key.like("basil:daily-challenge:%"),
        )
        .order_by(game_resource_events.c.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    day = date.fromisoformat(row.payload["challengeDay"])
    if day < today - timedelta(days=1):
        return None
    return DailyChallengeResult(
        challenge_day=day,
        scene_title=SCENE_TITLES.get(row.payload.get("sceneKey"), "Daily challenge"),
        rank=row.payload["rank"],
        participant_count=row.payload["participants"],
        basil=row.basil_delta,
    )


def challenge_snapshot(c, user_id: UUID) -> DailyChallengeResponse:
    today = challenge_day()
    scene_key, scene_title, scene_phrase = scene_for(today)
    entries = c.execute(
        select(challenge_entries.c.session_id, challenge_entries.c.completed_at, sessions.c.status)
        .join(sessions, sessions.c.id == challenge_entries.c.session_id)
        .where(
            challenge_entries.c.user_id == user_id,
            challenge_entries.c.challenge_day == today,
        )
        .order_by(challenge_entries.c.created_at.desc())
    ).all()
    completed = next((row for row in entries if row.completed_at is not None), None)
    open_entry = next((row for row in entries if row.status not in TERMINAL), None)
    status = "completed" if completed else "inProgress" if open_entry else "notStarted"
    session_id = (completed or open_entry).session_id if (completed or open_entry) else None
    participants = c.execute(
        select(func.count()).select_from(challenge_entries).where(
            challenge_entries.c.challenge_day == today,
            challenge_entries.c.completed_at.is_not(None),
        )
    ).scalar_one()
    joined = c.execute(
        select(func.count(func.distinct(challenge_entries.c.user_id))).where(
            challenge_entries.c.challenge_day == today,
        )
    ).scalar_one()
    mine = set(
        c.execute(
            select(challenge_finds.c.label_key).where(
                challenge_finds.c.challenge_day == today,
                challenge_finds.c.user_id == user_id,
            )
        ).scalars()
    )
    count = func.count().label("count")
    words = c.execute(
        select(
            challenge_finds.c.label_key,
            # The spelling most finders used, e.g. "coffee" over one "Coffee".
            func.mode().within_group(challenge_finds.c.label).label("label"),
            count,
        )
        .where(challenge_finds.c.challenge_day == today)
        .group_by(challenge_finds.c.label_key)
        .order_by(count.desc(), challenge_finds.c.label_key)
        .limit(WORDS_SHOWN)
    ).all()
    return DailyChallengeResponse(
        challenge_day=today,
        scene_key=scene_key,
        scene_title=scene_title,
        scene_phrase=scene_phrase,
        day_ends_at=day_ends_at(today),
        status=status,
        session_id=session_id,
        participant_count=participants,
        joined_count=joined,
        words=[
            DailyChallengeWord(label=row.label, count=row.count, found_by_you=row.label_key in mine)
            for row in words
        ],
        your_word_count=len(mine),
        last_result=_last_result(c, user_id, today),
    )
