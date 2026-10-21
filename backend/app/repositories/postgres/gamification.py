"""Accepted question rewards and immutable mission-batch evidence."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, timedelta
from uuid import uuid5

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.missions import get_mission, mission_definitions
from app.repositories.postgres.game_resources import (
    game_resource_events,
    resource_snapshot,
    reward_basil,
)
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import scene_object_relations, scene_objects
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.practice import PracticeConflictError
from app.schemas.base import utc_now
from app.schemas.gamification import (
    BasilTotals,
    GamificationSummary,
    MissionBadgePublic,
    MissionBatchPublic,
)
from app.schemas.tasks import SessionTask
from app.services.mission_eligibility import lesson_missions

POLICY_VERSION = "basil-questions.v1"
BADGE_POLICY_VERSION = "mission-badges.v1"
metadata = MetaData()
question_events = Table(
    "learning_question_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid, nullable=False),
    Column("session_id", Uuid, nullable=False),
    Column("task_id", Uuid, nullable=False),
    Column("question_id", String(100), nullable=False),
    Column("answer", Text, nullable=False),
    Column("is_correct", Boolean, nullable=False),
    Column("basil_earned", Integer, nullable=False),
    Column("policy_version", String(40), nullable=False),
    Column("mission_id", String(3)),
    Column("practice_level", String(2)),
    Column("content_version", Integer),
    Column("outcome", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
mission_batches = Table(
    "mission_batch_results",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("language_profile_id", Uuid, nullable=False),
    Column("session_id", Uuid, nullable=False),
    Column("mission_id", String(3), nullable=False),
    Column("practice_level", String(2), nullable=False),
    Column("content_version", Integer, nullable=False),
    Column("policy_version", String(40), nullable=False),
    Column("successful", Boolean, nullable=False),
    Column("lower_assistance", Boolean, nullable=False),
    Column("photo_identity", String(160)),
    Column("scenario_identity", String(64), nullable=False),
    Column("evidence", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)
photo_identities = Table(
    "learning_photo_identities",
    metadata,
    Column("media_asset_id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)

CATALOGUE = (
    ("M01", "Spot & Say", "Identify and describe"),
    ("M02", "Seek & Find", "Find and locate"),
    ("M03", "Count Me In", "Count and quantify"),
    ("M04", "Mine & Yours", "Talk about belongings"),
    ("M05", "Pick Your Flavor", "Express preferences and choose"),
    ("M06", "Ask Away", "Request and obtain something"),
    ("M07", "What’s the Price?", "Ask about prices"),
    ("M08", "The Daily Dish", "Talk about actions and routines"),
    ("M09", "Let Me Rephrase", "Correct a misunderstanding"),
    ("M10", "Problem Solver", "Report a problem"),
    ("M11", "Pass It On", "Leave a practical message"),
    ("M12", "Make It Happen", "Arrange an activity"),
)


def question_event(c, user_id, task_id, question_id):
    return (
        c.execute(
            select(question_events).where(
                question_events.c.user_id == user_id,
                question_events.c.task_id == task_id,
                question_events.c.question_id == question_id,
            )
        )
        .mappings()
        .first()
    )


def question_fingerprint(task, question_id):
    question = next(
        (item for item in task.public_content.questions if item.question_id == question_id), None
    )
    if question is None:
        raise PracticeConflictError(
            "This question changed. Start a new practice to answer the new version."
        )
    evaluation = next(
        (item for item in task.answer_key.question_evaluations if item.question_id == question_id),
        None,
    )
    payload = {
        "question": question.model_dump(mode="json", by_alias=True),
        "expected": task.answer_key.correct_option_ids.get(question_id),
        "evaluation": evaluation.model_dump(mode="json", by_alias=True) if evaluation else None,
        "acceptedTextAnswers": task.answer_key.accepted_text_answers_by_question.get(question_id),
        "statementCorrect": task.answer_key.statement_correct.get(question_id),
        "mission": task.public_content.mission_key,
    }
    # Only keys that accept alternatives carry them, so earlier fingerprints still match.
    if accepted := task.answer_key.accepted_option_ids.get(question_id):
        payload["acceptedOptionIds"] = accepted
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def compatible_question(event, task, question_id):
    if event and event["outcome"].get("contentFingerprint") != question_fingerprint(
        task, question_id
    ):
        raise PracticeConflictError(
            "This question changed. Start a new practice to answer the new version."
        )
    return event


def m06_check_supports(saved):
    step_support = {
        "replayAudio": "audio",
        "visualDetail": "hint",
        "phraseOnset": "clueFrame",
        "chunkBank": "wordBank",
        "fullModel": "answerReveal",
    }
    supports = list(dict.fromkeys(
        step_support[step] for step in saved.get("assistance", []) if step in step_support
    ))
    # An earlier incorrect answer receives a targeted hint before the next attempt.
    if any(attempt.get("isCorrect") is False for attempt in saved.get("attempts", [])[:-1]):
        if "hint" not in supports:
            supports.append("hint")
    return supports


def record_question(c, user_id, session, task, question_id, answer, is_correct, outcome):
    """Caller holds the account/session locks. One reward survives task regeneration."""
    prior = compatible_question(question_event(c, user_id, task.id, question_id), task, question_id)
    if prior:
        return prior
    assessed = (
        outcome.get("evidenceType") != "participation"
        and outcome.get("outcome") != "unassessed"
    )
    amount = (10 if is_correct else 5) if session.mode == "lesson" and assessed else 0
    content = task.public_content
    event_id = uuid5(task.id, f"question:{question_id}")
    c.execute(
        insert(question_events).values(
            id=event_id,
            user_id=user_id,
            language_profile_id=session.language_profile_id,
            session_id=session.id,
            task_id=task.id,
            question_id=question_id,
            answer=answer,
            is_correct=is_correct,
            basil_earned=amount,
            policy_version=POLICY_VERSION,
            mission_id=content.mission_id,
            practice_level=content.practice_level,
            content_version=content.content_version,
            outcome={**outcome, "contentFingerprint": question_fingerprint(task, question_id)},
            created_at=utc_now(),
        )
    )
    if amount:
        reward_basil(
            c,
            user_id,
            f"question:{task.id}:{question_id}",
            amount=amount,
            payload={
                "policyVersion": POLICY_VERSION,
                "languageProfileId": str(session.language_profile_id),
                "sessionId": str(session.id),
                "taskId": str(task.id),
                "questionId": question_id,
            },
        )
    return question_event(c, user_id, task.id, question_id)


def basil_totals(c, user_id):
    now = utc_now().astimezone(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    earned = game_resource_events.c.kind == "basilEarned"
    lifetime = c.execute(
        select(func.coalesce(func.sum(game_resource_events.c.basil_delta), 0)).where(
            game_resource_events.c.user_id == user_id,
            earned,
        )
    ).scalar_one()
    today = c.execute(
        select(func.coalesce(func.sum(game_resource_events.c.basil_delta), 0)).where(
            game_resource_events.c.user_id == user_id,
            earned,
            game_resource_events.c.created_at >= start,
            game_resource_events.c.created_at < start + timedelta(days=1),
        )
    ).scalar_one()
    return BasilTotals(
        today=today,
        lifetime=lifetime,
        balance=resource_snapshot(c, user_id).basil_leaves,
        competition_day=start.date(),
        day_ends_at=start + timedelta(days=1),
    )


def session_basil(c, user_id, session_id):
    task_keys = select(func.concat("basil:task:", session_tasks.c.id)).where(
        session_tasks.c.session_id == session_id,
    )
    return c.execute(
        select(func.coalesce(func.sum(game_resource_events.c.basil_delta), 0)).where(
            game_resource_events.c.user_id == user_id,
            game_resource_events.c.kind == "basilEarned",
            or_(game_resource_events.c.payload["sessionId"].astext == str(session_id),
                game_resource_events.c.source_key.in_(task_keys)),
        )
    ).scalar_one()


def task_basil(c, user_id, task_id):
    return c.execute(select(func.coalesce(func.sum(game_resource_events.c.basil_delta), 0)).where(
        game_resource_events.c.user_id == user_id,
        game_resource_events.c.kind == "basilEarned",
        or_(game_resource_events.c.payload["taskId"].astext == str(task_id),
            game_resource_events.c.source_key == f"basil:task:{task_id}"),
    )).scalar_one()


def _photo_identity(c, session):
    asset = (
        c.execute(
            select(media_assets).where(
                media_assets.c.id == session["scene_media_asset_id"],
            )
        )
        .mappings()
        .one()
    )
    if asset["source"] == "preloaded":
        return f"curated:{asset['id']}"
    digest = c.execute(
        select(photo_identities.c.content_hash).where(
            photo_identities.c.media_asset_id == asset["id"],
            photo_identities.c.user_id == session["user_id"],
        )
    ).scalar_one_or_none()
    return f"photo:{digest}" if digest else None


def _batch(c, session, key, tasks):
    mission = get_mission(*key)
    if mission is None:
        return None, None
    outcomes, expected_questions = [], []
    all_completed = all(task.status == "completed" for task in tasks)
    terminal = all(task.status in {"completed", "skipped"} for task in tasks)
    for task in tasks:
        evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
        expected_questions.extend(
            (task.id, item.question_id)
            for item in task.public_content.questions
            if item.question_id in evaluations
            and evaluations[item.question_id].evidence_type != "participation"
        )
        latest = c.execute(
            select(task_attempts.c.evaluation_details)
            .where(
                task_attempts.c.session_task_id == task.id,
            )
            .order_by(task_attempts.c.attempt_number.desc())
            .limit(1)
        ).scalar_one_or_none()
        if task.status == "completed" and latest:
            outcomes.extend(latest.get("questionOutcomes", []))
            continue
        checks = (session["analysis_draft"] or {}).get("missionChecks", {}).get(str(task.id), {})
        for question in task.public_content.questions:
            event = question_event(c, session["user_id"], task.id, question.question_id)
            if (
                not event
                or event["outcome"].get("contentFingerprint")
                != question_fingerprint(task, question.question_id)
            ):
                continue
            evaluation = evaluations.get(question.question_id)
            if not evaluation:
                continue
            saved = checks.get(question.question_id, {})
            correct = saved.get("isCorrect", event["is_correct"])
            built_in = question.interaction_type == "sentenceBuilding"
            supports = m06_check_supports(saved) if mission.mission_id == "M06" else []
            assistance = any(mission.counts_as_assistance(item) for item in supports) or (
                built_in and mission.counts_as_assistance("wordBank")
            )
            outcomes.append(
                dict(
                    questionId=question.question_id,
                    outcome="correct" if correct else "incorrect",
                    targetIds=evaluation.target_ids,
                    objectiveId=evaluation.objective_id,
                    evidenceType=evaluation.evidence_type,
                    assistanceUsed=assistance,
                )
            )
    assessed = [
        item
        for item in outcomes
        if item.get("outcome") in {"correct", "incorrect"}
        and item.get("evidenceType") != "participation"
    ]
    correct = [item for item in assessed if item["outcome"] == "correct"]
    independent = [item for item in correct if not item.get("assistanceUsed", True)]
    targets = {target for item in correct for target in item.get("targetIds", [])}
    requirements = []
    performance = mission.expected_performance
    if len(assessed) < len(expected_questions):
        requirements.append("Answer every assessed question in this mission.")
    if len(assessed) < performance.min_assessed_questions:
        requirements.append(
            f"Complete at least {performance.min_assessed_questions} assessed questions."
        )
    if not assessed or len(correct) / len(assessed) < performance.min_correct_ratio:
        requirements.append(f"Get at least {round(performance.min_correct_ratio * 100)}% correct.")
    if len(independent) < performance.min_independent_correct:
        requirements.append(
            f"Answer {performance.min_independent_correct} questions correctly without assistance."
        )
    if any(not targets.intersection(group) for group in performance.required_target_groups):
        requirements.append("Show the mission's required language targets correctly.")
    preparing = session["status"] == "generatingTasks"
    if preparing:
        requirements.append("Wait for the mission to finish preparing.")
    if not all_completed:
        requirements.append("Complete the mission's tasks without skipping.")
    success = not requirements
    total = len(expected_questions)
    percent = 100 if success else min(90, round(90 * len(assessed) / max(1, total)))
    public = MissionBatchPublic(
        mission_id=key[0],
        practice_level=key[1],
        content_version=key[2],
        percent=percent,
        status="ready" if success else "review" if terminal and not preparing else "inProgress",
        assessed_questions=len(assessed),
        correct_questions=len(correct),
        total_questions=total,
        independent_correct=len(independent),
        requirements=requirements,
    )
    relation_types = sorted(
        set(
            c.execute(
                select(scene_object_relations.c.relation)
                .join(
                    scene_objects,
                    scene_objects.c.id == scene_object_relations.c.subject_scene_object_id,
                )
                .where(scene_objects.c.session_id == session["id"])
            ).scalars()
        )
    )
    quantities = sorted(
        {
            item.get("quantity")
            for item in (session["analysis_draft"] or {}).get("countedGroups", [])
            if isinstance(item.get("quantity"), int)
        }
    )
    scenario = sorted(
        {
            f"{item.get('objectiveId')}:{target}:{item.get('evidenceType')}"
            for item in assessed
            for target in item.get("targetIds", [])
        }
    )
    evidence = dict(
        public.model_dump(mode="json", by_alias=True),
        outcomes=outcomes,
        originalSpokenProduction=False,
        followUpProduction=False,
    )
    record = (
        dict(
            id=uuid5(session["id"], f"mission-batch:{key}"),
            user_id=session["user_id"],
            language_profile_id=session["language_profile_id"],
            session_id=session["id"],
            mission_id=key[0],
            practice_level=key[1],
            content_version=key[2],
            policy_version=BADGE_POLICY_VERSION,
            successful=success,
            lower_assistance=bool(assessed) and len(independent) / len(assessed) >= 0.75,
            photo_identity=_photo_identity(c, session),
            scenario_identity=hashlib.sha256(
                json.dumps([scenario, relation_types, quantities]).encode()
            ).hexdigest(),
            evidence=evidence,
            created_at=utc_now(),
        )
        if terminal and not preparing
        else None
    )
    return public, record


def session_missions(c, user_id, session_id, *, persist=False):
    session = (
        c.execute(
            select(sessions).where(
                sessions.c.id == session_id,
                sessions.c.user_id == user_id,
            )
        )
        .mappings()
        .first()
    )
    if session is None:
        return None
    groups = defaultdict(list)
    for row in c.execute(
        select(session_tasks).where(
            session_tasks.c.session_id == session_id,
        )
    ).mappings():
        task = SessionTask.model_validate(dict(row))
        if task.public_content.mission_key and task.kind == "grammarLesson":
            groups[task.public_content.mission_key].append(task)
    result = []
    for key, tasks in groups.items():
        public, record = _batch(c, session, key, tasks)
        if public:
            result.append(public)
        if persist and record:
            c.execute(insert(mission_batches).values(**record).on_conflict_do_nothing())
    return result


def gamification_summary(c, user_id, profile):
    rows = (
        c.execute(
            select(mission_batches).where(
                mission_batches.c.user_id == user_id,
                mission_batches.c.language_profile_id == profile["id"],
                mission_batches.c.successful.is_(True),
            )
        )
        .mappings()
        .all()
    )
    definitions = list(mission_definitions().values())
    implemented = {mission.mission_id for mission in lesson_missions("lesson", profile)}
    catalogue = list(CATALOGUE)
    extras = {
        definition.mission_id: definition
        for definition in definitions
        if definition.mission_id not in {item[0] for item in catalogue}
    }
    catalogue.extend(
        (key, definition.title, definition.objective.can_do)
        for key, definition in sorted(extras.items())
    )
    badges = []
    for mission_id, name, skill in catalogue:
        successes = [row for row in rows if row["mission_id"] == mission_id]
        photos = {row["photo_identity"] for row in successes if row["photo_identity"]}
        scenarios = {row["scenario_identity"] for row in successes if row["photo_identity"]}
        independent_photos = {
            row["photo_identity"]
            for row in successes
            if row["photo_identity"] and row["lower_assistance"]
        }
        cook = len(photos) >= 3 and len(scenarios) >= 2 and len(independent_photos) >= 2
        level = "Cook" if cook else "Taster" if successes else None
        requirements = (
            ["Complete a successful mission batch to earn Taster."]
            if not successes
            else [
                "Complete successful batches across three different photos and two target sets.",
                "In two different photos, answer at least 75% correctly without assistance.",
            ]
            if not cook
            else []
        )
        requirements.append(
            "Chef and higher levels require original spoken responses and follow-ups; "
            "these levels will become available with spoken missions."
        )
        badges.append(
            MissionBadgePublic(
                mission_id=mission_id,
                name=name,
                skill=skill,
                available=mission_id in implemented,
                practice_level=profile["proficiency_level"],
                badge_level=level,
                successful_batches=len(successes),
                distinct_photos=len(photos),
                requirements=requirements,
            )
        )
    return GamificationSummary(
        policy_version=POLICY_VERSION, basil=basil_totals(c, user_id), missions=badges
    )
