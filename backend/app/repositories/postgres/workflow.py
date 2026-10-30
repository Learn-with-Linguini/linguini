"""Atomic normalized session workflow. Locks serialize each user's transitions."""

import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, and_, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

from app.ai.cache import CacheScope, TemplateSet
from app.ai.features.ispy_clues import ISpyClueGenerationError
from app.ai.features.ispy_guess import ISpyGuessError, ISpyGuessResult
from app.ai.features.learning_tasks import required_task_focuses
from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.ai.features.scene_analysis import (
    SCENE_ANALYSIS_PROMPT_VERSION,
    SCENE_ANALYSIS_SCHEMA_VERSION,
    RoutedSceneAnalyzer,
)
from app.missions import get_mission
from app.repositories.postgres.daily_challenges import enter_challenge, record_completion
from app.repositories.postgres.game_resources import refund_sauce, reward_basil
from app.repositories.postgres.gamification import (
    compatible_question,
    m06_check_supports,
    photo_identities,
    question_event,
    question_events,
    record_question,
    session_basil,
    session_missions,
    task_basil,
)
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.learner_history import snapshot_learner_history
from app.repositories.postgres.media_assets import media_assets, media_scene_analyses
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import (
    object_values,
    scene_object_relations,
    scene_objects,
)
from app.repositories.postgres.scenes import preloaded_scenes
from app.repositories.postgres.tasks import (
    entity_values,
    session_tasks,
    task_attempts,
    task_evaluation_claims,
)
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import (
    record_vocabulary_evidence,
    user_vocabulary_progress,
    vocabulary_encounters,
    vocabulary_items,
    vocabulary_translations,
)
from app.repositories.postgres.xp import award, xp_events
from app.repositories.practice import (
    ActiveSessionLimitReachedError,
    DailyLessonLimitReachedError,
    InsufficientSceneError,
    LessonLanguageUnavailableError,
    PracticeConflictError,
    PracticeNotFoundError,
    PracticeStorageError,
)
from app.schemas.base import utc_now
from app.schemas.enums import (
    AccountTier,
    SessionMode,
    SessionStatus,
    VocabularyEncounterOutcome,
    VocabularyEncounterType,
)
from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.schemas.missions import MissionDefinition
from app.schemas.roleplay import parse_roleplay_facts
from app.schemas.sessions import (
    CountedGroup,
    Session,
    SessionDetailResponse,
    SessionSummaryResponse,
)
from app.schemas.tasks import (
    ISPY_DESCRIPTION_EVALUATION_VERSION,
    CheckVocabularyAnswerResponse,
    CheckVocabularyTypingResponse,
    ISpyDescriptionEvaluation,
    LessonAnswerCheck,
    LessonAssistanceResponse,
    LessonChecksResponse,
    MissionScenarioResponse,
    QuestionOutcome,
    SessionProgress,
    SessionTask,
    SessionTaskPublic,
    TaskActionResponse,
    TaskAttempt,
    VocabularyChecksResponse,
)
from app.schemas.translation import SceneTranslationResult
from app.schemas.vocabulary import (
    VocabularyEncounter,
    VocabularyItem,
    VocabularyTranslation,
)
from app.services.background import InlineBackgroundRunner
from app.services.ispy_clue_frames import check_clue
from app.services.ispy_descriptions import (
    EVALUATION_FAILED_MESSAGE,
    OUTCOME_CORRECTNESS,
    interpret_guess,
)
from app.services.mission_eligibility import (
    SHORTFALL_KINDS,
    SceneShortfall,
    lesson_mission,
    lesson_missions,
    mission_snapshot,
    plan_missions,
    provisional_mission_focus,
    saved_counted_groups,
    scene_shortfall,
    snapshot_missions,
)
from app.services.mission_roleplay import assign_a0_scenario, assign_roleplay
from app.services.quantities import suggested_quantity
from app.services.question_outcomes import (
    normalize_answer,
    offered_supports,
    review_details,
    word_results,
)
from app.services.scene_analysis import (
    DeterministicSceneAnalyzer,
    UnavailableSceneAnalyzer,
    scene_inventory,
    scene_result_from_inventory,
    uploaded_scene_title,
)
from app.services.session_personalization import (
    lesson_history,
    personalization_summary,
    personalize_introduction,
)
from app.services.session_plan import (
    bootstrap_word,
    build_grammar_lessons,
    build_ispy_clue_tasks,
    build_ispy_description_tasks,
    build_tasks,
)

logger = logging.getLogger(__name__)


def _unique_by_id(items):
    """Keep the first occurrence of entities that share an ID."""
    seen = set()
    unique = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        unique.append(item)
    return unique


TERMINAL = {"completed", "abandoned", "failed"}
MAX_ACTIVE_SESSIONS = 3
MAX_ANALYSIS_ATTEMPTS = 3
ALLOWED_TRANSITIONS = {
    "created": {"analyzingScene", "abandoned", "failed"},
    "analyzingScene": {"awaitingObjectReview", "abandoned", "failed"},
    "awaitingObjectReview": {"analyzingScene", "generatingTasks", "abandoned", "failed"},
    "generatingTasks": {"awaitingObjectReview", "ready", "inProgress", "abandoned", "failed"},
    "ready": {"inProgress", "abandoned", "failed"},
    "inProgress": {"completed", "abandoned", "failed"},
    "completed": set(),
    "abandoned": set(),
    "failed": {"analyzingScene"},
}
READ_TASKS = {"vocabularyIntroduction", "grammarExplanation", "syntaxExplanation"}
ANALYSIS_TIMEOUT = timedelta(minutes=2)


def _lesson_answer_is_correct(task, question_id, answer):
    question = next(
        item for item in task.public_content.questions if item.question_id == question_id
    )
    expected = task.answer_key.correct_option_ids.get(question_id)
    interaction_type = getattr(question, "interaction_type", None)
    if (
        getattr(question, "typed_allowed", False)
        and normalize_answer(answer) in {
            normalize_answer(item)
            for item in task.answer_key.accepted_text_answers_by_question.get(question_id, [])
        }
    ):
        return True
    if interaction_type == "textCloze":
        import unicodedata

        def fold(value):
            return "".join(
                char
                for char in unicodedata.normalize("NFKD", value.casefold())
                if not unicodedata.combining(char)
            ).strip(" .?!")

        state = (task.answer_key.mission_state or {}).get("answers", {}).get(question_id, {})
        accepted = [expected, *state.get("accepted", [])]
        return fold(answer) in {fold(value) for value in accepted if value}
    return (
        normalize_answer(answer) == normalize_answer(expected)
        if interaction_type == "sentenceBuilding"
        else answer == expected
        or answer in task.answer_key.accepted_option_ids.get(question_id, ())
    )


def _m06_feedback(transaction, question_id, wrong_field):
    mismatch = transaction.get("mismatch") or {}
    if question_id == "m06-q6":
        if mismatch.get("flag"):
            field = mismatch.get("field", "detail")
            label = {
                "quantity": "quantity",
                "size": "size",
                "item": "item",
                "temperature": "temperature",
                "serviceSetting": "service setting",
                "colour": "colour",
            }.get(field, "detail")
            return field, f"The server got the {label} wrong — correct it."
        return "confirmOrRepair", "The server repeated your order correctly — confirm it."

    if wrong_field in {"request", "functionalChunk"}:
        return wrong_field, "Use the polite request phrase."
    if wrong_field in {"other detail", "followUp"}:
        wrong_field = transaction.get("followUp", {}).get("type")
    if wrong_field == "quantity":
        value = {1: "one", 2: "two", 3: "three"}.get(
            transaction.get("quantity"), "the correct amount"
        )
        return wrong_field, f"Check the quantity — the order was for {value}."
    if wrong_field == "size":
        value = transaction.get("requestDetails", {}).get("size") or transaction.get(
            "followUp", {}
        ).get("value", "unknown")
        return wrong_field, f"Check the size — the order was {value}."
    if wrong_field == "item":
        value = transaction.get("itemLabel", "that item")
        return wrong_field, f"Check the item — the order was for {value}."
    if wrong_field == "temperature":
        value = transaction.get("followUp", {}).get("value", "the requested temperature")
        return wrong_field, f"Check hot or cold — you wanted it {value}."
    if wrong_field == "serviceSetting":
        value = "to take away" if transaction.get("serviceSetting") == "takeAway" else "to eat in"
        return wrong_field, f"Check eat in or take away — you wanted it {value}."
    if wrong_field == "colour":
        value = transaction.get("followUp", {}).get("value", "the requested colour")
        return wrong_field, f"Check the colour — you wanted {value}."
    follow_type = transaction.get("followUp", {}).get("type")
    label = {
        "serviceSetting": "eat in or take away",
        "temperature": "hot or cold",
        "size": "size",
        "colour": "colour",
    }.get(follow_type, "detail")
    return "followUp", f"Listen for the detail the server asks about: {label}."


_REVIEW_STATUSES = {"created", "analyzingScene", "awaitingObjectReview"}


def review_marker_numbers(detected, accepted_ids, added_ids, suggested_ids=None):
    """Keep marker numbers from the initially visible review subset."""
    accepted = {str(item) for item in accepted_ids}
    suggested = {str(item) for item in suggested_ids or []}
    initially_visible = [
        obj for obj in detected if not suggested or str(obj["id"]) in suggested
    ]
    numbers = {
        str(obj["id"]): number for number, obj in enumerate(initially_visible, 1)
        if str(obj["id"]) in accepted
    }
    numbers.update({
        str(item): max(numbers.values(), default=0) + number
        for number, item in enumerate(added_ids, 1)
    })
    return numbers


def task_progress(tasks):
    complete = sum(t.status == "completed" for t in tasks)
    skipped = sum(t.status == "skipped" for t in tasks)
    return SessionProgress(
        completed_task_count=complete,
        skipped_task_count=skipped,
        terminal_task_count=complete + skipped,
        total_task_count=len(tasks),
    )


def is_curated_content(session_id, content, objects, relations):
    """Whether reviewed objects and relations are unchanged curated content.

    Curated objects keep their ``curated:`` IDs, labels and attributes, and
    only unchanged server suggestions keep a ``source_relation_key``.
    """
    items = {
        uuid5(session_id, "curated:" + str(entry["id"])): entry
        for entry in (content or {}).get("items", [])
    }
    for obj in objects:
        entry = items.get(obj.id)
        if (
            entry is None
            or obj.label != entry["translation"]
            or (obj.attributes or None) != (entry.get("attributes") or None)
        ):
            return False
    return all(row.source_relation_key for row in relations)


def translation_payload(target_language, title, summary, objects, relations):
    """The scene-translation payload for reviewed ``objects`` and ``relations``."""
    return {
        "targetLanguage": target_language,
        "sceneTitle": title,
        "sceneSummary": summary,
        "objects": [{"key": str(obj.id), "source": obj.label} for obj in objects],
        "attributes": [
            {"key": f"{obj.id}:{attribute_type}", "source": value}
            for obj in objects
            for attribute_type, value in (obj.attributes or {}).items()
            if isinstance(value, str) and value.strip()
        ],
        "relationships": [{"key": str(row.id), "source": row.relation} for row in relations],
    }


def learning_task_payload(translation_payload, translated_scene, scene_relations=()):
    """Reuse the translator payload, carrying the target-language terms it produced."""
    payload = {
        "targetLanguage": translation_payload["targetLanguage"],
        "sceneTitle": translation_payload["sceneTitle"],
        "sceneSummary": translation_payload["sceneSummary"],
        **{
            field: [
                term.model_dump(mode="json", by_alias=True, exclude_none=True)
                for term in getattr(translated_scene, field)
            ]
            for field in ("objects", "attributes", "relationships")
        },
    }
    relation_links = {str(row.id): row for row in scene_relations}
    for term in payload["relationships"]:
        if row := relation_links.get(term["key"]):
            term["subjectObjectKey"] = str(row.subject_scene_object_id)
            term["referenceObjectKey"] = str(row.reference_scene_object_id)
    for term in payload["attributes"]:
        term["objectKey"] = term["key"].rsplit(":", 1)[0]
    payload["requiredTaskFocuses"] = list(required_task_focuses(payload))
    return payload


def ispy_clue_payload(translation_payload, translated_scene, objects, scene_relations=()):
    """Give the clue model translated scene facts and positions, never the image itself."""
    payload = learning_task_payload(translation_payload, translated_scene, scene_relations)
    positions = {
        str(obj.id): (
            obj.bounding_box.model_dump() if obj.bounding_box is not None else {}
        )
        for obj in objects
    }
    for item in payload["objects"]:
        box = positions.get(item["key"], {})
        item["anchorPoint"] = {
            "x": round(float(box.get("x", 0.5)) + float(box.get("width", 0)) / 2, 3),
            "y": round(float(box.get("y", 0.5)) + float(box.get("height", 0)) / 2, 3),
        }
    payload.pop("requiredTaskFocuses", None)
    return payload


def _ispy_guess_context(translation_payload, translated_scene, objects, scene_relations=()):
    """Persist translated scene facts; never persist or send a selected target."""
    payload = ispy_clue_payload(
        translation_payload, translated_scene, objects, scene_relations
    )
    return {
        "targetLanguage": payload["targetLanguage"],
        "sceneObjects": {
            "objects": payload["objects"],
            "attributes": payload["attributes"],
            "relations": payload["relationships"],
        },
    }


def analysis_attempts(session):
    return (session.analysis_draft or {}).get("analysisAttempts", 1)


def analysis_retryable(session):
    """A temporary scene-analysis failure can rerun on the saved image."""
    return (
        session.status == "failed"
        and session.failure_code == "sceneAnalysisFailed"
        and analysis_attempts(session) < MAX_ANALYSIS_ATTEMPTS
    )


def parse_session(row):
    return Session.model_validate({k: row[k] for k in Session.model_fields})


PROCESSING_STATUSES = ("analyzingScene", "generatingTasks")
PROCESSING_FAILURE_CODES = {
    "analyzingScene": "sceneAnalysisFailed",
    "generatingTasks": "taskGenerationFailed",
}


def _stale_processing(status=None):
    """The one staleness predicate shared by the read check, `_active_row` and `_reap`."""
    return and_(
        sessions.c.status == status if status else sessions.c.status.in_(PROCESSING_STATUSES),
        sessions.c.analysis_draft["processingStartedAt"].astext.cast(DateTime(timezone=True))
        < utc_now() - ANALYSIS_TIMEOUT,
    )


_LANGUAGE_CONTEXT_UNSET = object()


def session_language_context(session, profile):
    """The pack context a session runs with: its saved snapshot, else the profile's pack.

    A session saved with a pack that no longer passes its release gates cannot resume;
    it is refused like a new lesson, never rebuilt by another builder.
    """
    from app.language_packs.context import operation_context

    snapshot = (session.analysis_draft or {}).get("languageContext")
    if snapshot is None:
        return operation_context(session.mode, profile)
    try:
        return operation_context(session.mode, profile, snapshot)
    except ValueError as error:
        raise LessonLanguageUnavailableError(
            "Photo lessons aren't available for this language yet."
        ) from error


@dataclass(frozen=True)
class GenerationClaim:
    """An immutable snapshot taken when a task-generation revision was claimed."""

    session_id: UUID
    profile_id: UUID
    revision: int
    session: Session
    profile: dict
    title: str
    objects: list[SceneObject]
    relations: list[SceneObjectRelation]
    cache_scope: CacheScope | None = None
    templates: TemplateSet | None = None
    learner_history: dict | None = None
    missions: tuple[MissionDefinition, ...] = ()
    counted_groups: tuple[dict, ...] = ()
    mission_progress: dict | None = None
    roleplay_facts: dict[str, list[dict]] | None = None
    learner_facts: dict[str, dict] | None = None
    review_markers: dict[str, int] | None = None
    language_context: object | None = None

    @property
    def generation_options(self) -> dict:
        """Keyword arguments for the generation services."""
        options = {"cache_scope": self.cache_scope}
        if self.templates:
            options["templates"] = self.templates
        return options


@dataclass(frozen=True)
class DescriptionClaim:
    """The target-blind inputs of a claimed I-Spy description attempt."""

    task_id: UUID
    attempt_id: UUID
    context: dict
    learner_text: str
    session_id: str


@dataclass(frozen=True)
class PendingEvaluation:
    """Another request with the same idempotency key holds the evaluation lease."""

    task_id: UUID
    attempt_id: UUID


DEFAULT_EVALUATION_SECONDS = 120
EVALUATION_LEASE_MARGIN_SECONDS = 15
EVALUATION_POLL_SECONDS = (0.02, 0.1)
NO_EVALUATION_CLAIM = dict(
    evaluation_claim_id=None,
    evaluation_claim_fingerprint=None,
    evaluation_claim_expires_at=None,
)


@dataclass(frozen=True)
class DescriptionEvaluation:
    attempt_id: UUID
    guess: ISpyGuessResult | None


@contextmanager
def _timed(stage, session_id):
    started = time.perf_counter()
    try:
        yield
    finally:
        logger.info(
            "Task generation %s took %.0f ms for session %s.",
            stage,
            (time.perf_counter() - started) * 1000,
            session_id,
        )


def _scene_title(session, scene):
    return session.session_title or (scene["title"] if scene else "Your uploaded photo")


def _translation_preview(session):
    preview = (session.analysis_draft or {}).get("translationPreview")
    return SceneTranslationResult.model_validate(preview) if preview else None


def _ai_provider(name):
    """A provider passed in directly, or built on first use by the shared AI runtime."""

    def get(self):
        provider = self._providers.get(name)
        if provider is None and self.ai is not None:
            return getattr(self.ai, name)()
        return provider

    def set(self, value):
        self._providers[name] = value

    return property(get, set)


class PostgresWorkflowRepository:
    translator = _ai_provider("translator")
    learning_task_generator = _ai_provider("learning_task_generator")
    ispy_clue_generator = _ai_provider("ispy_clue_generator")
    ispy_guess_generator = _ai_provider("ispy_guess_generator")

    def __init__(
        self,
        engine,
        user_id,
        analyzer=None,
        translator=None,
        learning_task_generator=None,
        ispy_clue_generator=None,
        ispy_guess_generator=None,
        background=None,
        ai=None,
    ):
        self.engine, self.user_id = engine, user_id
        self.ai = ai
        self._providers = {}
        self._analyzer = analyzer
        self.translator = translator
        self.learning_task_generator = learning_task_generator
        self.ispy_clue_generator = ispy_clue_generator
        self.ispy_guess_generator = ispy_guess_generator
        self.background = background or InlineBackgroundRunner()

    @property
    def analyzer(self):
        if self._analyzer is None:
            deterministic = DeterministicSceneAnalyzer(self.engine)
            uploaded = self.ai.uploaded_scene_analyzer() if self.ai else None
            self._analyzer = RoutedSceneAnalyzer(
                deterministic, uploaded or self._uploaded_fallback_analyzer()
            )
        return self._analyzer

    def _uploaded_fallback_analyzer(self):
        return UnavailableSceneAnalyzer()

    @analyzer.setter
    def analyzer(self, value):
        self._analyzer = value

    @contextmanager
    def transaction(self):
        started = time.perf_counter()
        try:
            with self.engine.begin() as connection:
                if (
                    connection.execute(
                        select(users.c.id).where(users.c.id == self.user_id).with_for_update()
                    ).scalar_one_or_none()
                    is None
                ):
                    raise PracticeNotFoundError("User not found.")
                yield connection
        except SQLAlchemyError as exc:
            raise PracticeStorageError("Unable to save the session workflow.") from exc
        finally:
            logger.debug(
                "Workflow transaction held the user lock for %.1f ms.",
                (time.perf_counter() - started) * 1000,
            )

    @contextmanager
    def read_connection(self):
        """Reads need a consistent snapshot, not the per-user write lock."""
        try:
            with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
                yield c
        except SQLAlchemyError as exc:
            raise PracticeStorageError("Unable to read the session workflow.") from exc

    def _session(self, c, session_id, profile_id=None):
        query = select(sessions).where(
            sessions.c.id == session_id, sessions.c.user_id == self.user_id
        )
        if profile_id:
            query = query.where(sessions.c.language_profile_id == profile_id)
        row = c.execute(query).mappings().one_or_none()
        if row is None:
            raise PracticeNotFoundError("Session not found.")
        return parse_session(row)

    def _transition(self, c, session, target, **extra):
        """Compare-and-set a session status; only listed edges are legal."""
        if session.status == target:
            return session
        if target not in ALLOWED_TRANSITIONS[session.status]:
            raise PracticeConflictError(
                f"Session cannot move from {session.status!r} to {target!r}."
            )
        values = dict(extra, status=target)
        if target in {"analyzingScene", "generatingTasks"}:
            # The session model has no updated_at; keep the processing clock in its draft.
            values["analysis_draft"] = {
                **(extra.get("analysis_draft", session.analysis_draft) or {}),
                "processingStartedAt": utc_now().isoformat(),
                **({"analysisStage": "loadingImage"} if target == "analyzingScene" else {}),
            }
        if target == "inProgress":
            values["started_at"] = session.started_at or utc_now()
        elif target == "completed":
            values["completed_at"] = utc_now()
        elif target == "abandoned":
            values["abandoned_at"] = utc_now()
        changed = c.execute(
            update(sessions)
            .where(sessions.c.id == session.id, sessions.c.status == session.status)
            .values(**values)
        ).rowcount
        if not changed:
            raise PracticeConflictError(
                "Session changed while this request was running. Retry the action."
            )
        practiced = target == "abandoned" and c.execute(
            select(task_attempts.c.id).join(
                session_tasks, session_tasks.c.id == task_attempts.c.session_task_id,
            ).where(session_tasks.c.session_id == session.id).limit(1)
        ).first()
        if session.mode == SessionMode.LESSON and (
            target == "failed"
            or (target == "abandoned" and session.started_at is None and not practiced)
        ):
            refund_sauce(c, self.user_id, self._sauce_key(session))
        return session.model_copy(update={**values, "status": SessionStatus(target)})

    @staticmethod
    def _sauce_key(session, attempt=None):
        return f"session:{session.id}:analysis:{attempt or max(1, analysis_attempts(session))}"

    def _tasks(self, c, session_id):
        return [
            SessionTask.model_validate(dict(r))
            for r in c.execute(
                select(session_tasks)
                .where(session_tasks.c.session_id == session_id)
                .order_by(session_tasks.c.order_index)
            ).mappings()
        ]

    def check_vocabulary_answer(self, task_id, question_id, option_id, review=False):
        """Check a choice; scene revisits are intentionally read-only practice."""
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            session = self._session(c, task.session_id)
            if task.kind != "vocabularyIntroduction" or not task.answer_key:
                raise PracticeConflictError("This task does not support answer checking.")
            question = next(
                (item for item in task.public_content.questions if item.question_id == question_id),
                None,
            )
            if question is None or option_id not in {item.option_id for item in question.options}:
                raise PracticeConflictError("Choose one of the offered answers.")
            expected = task.answer_key.correct_option_ids.get(question_id)
            if expected is None:
                raise PracticeConflictError("This question has no answer key.")
            prior = None if review else compatible_question(
                question_event(c, self.user_id, task.id, question_id), task, question_id
            )
            if (
                not prior
                and session.status in {"inProgress", "generatingTasks"}
                and task.status not in {"completed", "skipped"}
            ):
                prior = record_question(
                    c,
                    self.user_id,
                    session,
                    task,
                    question_id,
                    option_id,
                    expected == option_id,
                    {"evidenceType": "recognition"},
                )
            return CheckVocabularyAnswerResponse(
                question_id=question_id,
                accepted_option_id=prior["answer"] if prior else option_id,
                is_correct=prior["is_correct"] if prior else expected == option_id,
                correct_option_id=expected,
                basil_earned=prior["basil_earned"] if prior else 0,
            )

    def vocabulary_checks(self, task_id):
        with self.read_connection() as c:
            task = self._task_row(c, task_id)
            if task.kind != "vocabularyIntroduction" or not task.answer_key:
                raise PracticeConflictError("This task does not support vocabulary checks.")
            rows = c.execute(
                select(question_events).where(
                    question_events.c.user_id == self.user_id,
                    question_events.c.task_id == task_id,
                )
            ).mappings()
            return VocabularyChecksResponse(
                checks=[
                    CheckVocabularyAnswerResponse(
                        question_id=row["question_id"],
                        accepted_option_id=row["answer"],
                        is_correct=row["is_correct"],
                        basil_earned=row["basil_earned"],
                        correct_option_id=task.answer_key.correct_option_ids[row["question_id"]],
                    )
                    for row in rows
                    if row["question_id"] in task.answer_key.correct_option_ids
                    and compatible_question(row, task, row["question_id"])
                ]
            )

    def check_vocabulary_typing(
        self, task_id, learning_key, answer, reveal
    ) -> CheckVocabularyTypingResponse:
        with self.transaction() as c:
            row = (
                c.execute(
                    select(session_tasks)
                    .join(sessions, sessions.c.id == session_tasks.c.session_id)
                    .join(
                        language_profiles,
                        language_profiles.c.id == sessions.c.language_profile_id,
                    )
                    .where(
                        session_tasks.c.id == task_id,
                        sessions.c.user_id == self.user_id,
                        language_profiles.c.is_active.is_(True),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise PracticeNotFoundError("Task not found.")
            task = SessionTask.model_validate(dict(row))
            if task.kind != "vocabularyIntroduction" or not task.answer_key:
                raise PracticeConflictError("This task does not support typing checks.")
            accepted = task.answer_key.accepted_text_answers_by_vocabulary_id.get(learning_key)
            if not accepted:
                raise PracticeConflictError("This word has no typing answer key.")
            is_correct = not reveal and normalize_answer(answer) in {
                normalize_answer(candidate) for candidate in accepted
            }
            session = self._session(c, task.session_id)
            basil_earned = 0
            if (
                is_correct
                and session.mode == "lesson"
                and session.status in {"inProgress", "generatingTasks"}
                and task.status not in {"completed", "skipped"}
            ):
                basil_earned = reward_basil(
                    c,
                    self.user_id,
                    f"typing:{task.id}:{learning_key}",
                    amount=10,
                    payload={
                        "policyVersion": "basil-typing.v1",
                        "languageProfileId": str(session.language_profile_id),
                        "sessionId": str(session.id),
                        "taskId": str(task.id),
                        "learningKey": learning_key,
                        "isCorrect": is_correct,
                        "revealed": reveal,
                    },
                )
            return CheckVocabularyTypingResponse(
                learning_key=learning_key,
                is_correct=is_correct,
                correct_answer=accepted[0],
                revealed=reveal,
                basil_earned=basil_earned,
            )

    @staticmethod
    def _lesson_check(task, question_id, answer, is_correct, stored=None):
        question = next(
            item for item in task.public_content.questions if item.question_id == question_id
        )
        expected = task.answer_key.correct_option_ids.get(question_id)
        correct_answer = expected
        if question.interaction_type == "multipleChoice":
            correct_answer = next(
                option.label for option in question.options if option.option_id == expected
            )
        attempts = (stored or {}).get("attempts", [])
        locked = (stored or {}).get("locked", not question.allow_retry)
        attempts_left = max(0, 3 - len(attempts)) if question.allow_retry else None
        if question.allow_retry and not locked:
            correct_answer = None
        feedback = None
        wrong_field = None
        if not is_correct and question.allow_retry:
            state = task.answer_key.mission_state or {}
            answer_fields = state.get("distractorFields", {}).get(question_id, {})
            wrong_field = answer_fields.get(answer)
            if wrong_field is None and question.interaction_type == "sentenceBuilding":
                normalized = normalize_answer(answer)
                wrong_field = next(
                    (
                        field
                        for token, field in answer_fields.items()
                        if normalize_answer(token) in normalized
                    ),
                    None,
                )
            if task.public_content.mission_id == "M06":
                transaction = state.get("transaction", {})
                if wrong_field is None:
                    wrong_field = {
                        "m06-q3": "request",
                        "m06-q4": "followUp",
                        "m06-q5": transaction.get("followUp", {}).get("type"),
                        "m06-q6": (
                            transaction.get("mismatch", {}).get("field")
                            if transaction.get("mismatch", {}).get("flag")
                            else "confirmOrRepair"
                        ),
                    }.get(question_id, "request")
                wrong_field, feedback = _m06_feedback(transaction, question_id, wrong_field)
            elif wrong_field == "quantity":
                quantity = state.get("transaction", {}).get("quantity")
                feedback = f"Check the quantity — the order was for {quantity}."
            elif wrong_field:
                feedback = "Check that detail and try again."
        evaluation = next(
            item for item in task.answer_key.question_evaluations if item.question_id == question_id
        )
        supports = []
        if task.public_content.mission_id == "M06":
            supports = m06_check_supports(stored or {})
            if question.interaction_type == "sentenceBuilding" and "wordBank" not in supports:
                supports.append("wordBank")
        mission = (
            get_mission(*task.public_content.mission_key)
            if task.public_content.mission_key else None
        )
        return LessonAnswerCheck(
            basil_earned=(stored or {}).get("basilEarned", 0),
            question_id=question_id,
            answer=answer,
            is_correct=is_correct,
            correct_answer=correct_answer,
            attempts_left=attempts_left,
            feedback=feedback,
            wrong_field=wrong_field,
            assistance_steps_used=list((stored or {}).get("assistance", [])),
            outcome=QuestionOutcome(
                question_id=question_id,
                outcome="correct" if is_correct else "incorrect",
                objective_id=evaluation.objective_id,
                target_ids=evaluation.target_ids,
                evidence_type=evaluation.evidence_type,
                assistance=supports,
                assistance_used=any(
                    mission is None or mission.counts_as_assistance(item) for item in supports
                ),
            ),
        )

    def check_lesson_answer(self, task_id, question_id, answer):
        """Lock the first submitted answer without recording lesson evidence."""
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            if task.kind != "grammarLesson":
                raise PracticeConflictError("This lesson does not support per-question checking.")
            session_row = (
                c.execute(
                    select(sessions)
                    .where(sessions.c.id == task.session_id, sessions.c.user_id == self.user_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if session_row is None:
                raise PracticeNotFoundError("Task not found.")
            session = parse_session(session_row)
            draft = dict(session.analysis_draft or {})
            mission_checks = dict(draft.get("missionChecks") or {})
            task_checks = dict(mission_checks.get(str(task.id)) or {})
            stored = task_checks.get(question_id)
            persisted = compatible_question(
                question_event(c, self.user_id, task.id, question_id), task, question_id
            )
            if stored is None and persisted:
                stored = {
                    "answer": persisted["answer"],
                    "isCorrect": persisted["is_correct"],
                    "basilEarned": persisted["basil_earned"],
                    "locked": True,
                }
            if stored is not None and persisted:
                stored = {**stored, "basilEarned": persisted["basil_earned"]}
            question_ids = [item.question_id for item in task.public_content.questions]
            if question_id not in question_ids:
                raise PracticeConflictError("Choose a question from this lesson.")
            position = question_ids.index(question_id)
            question = task.public_content.questions[position]
            if stored is not None and (not question.allow_retry or stored.get("locked", False)):
                return self._lesson_check(
                    task, question_id, stored["answer"], stored["isCorrect"], stored
                )
            if any(
                question not in task_checks or not task_checks[question].get("locked", True)
                for question in question_ids[:position]
            ):
                raise PracticeConflictError("Check each lesson question in order.")
            if (
                question.interaction_type == "multipleChoice"
                and answer not in {option.option_id for option in question.options}
                and not question.typed_allowed
            ):
                raise PracticeConflictError("Choose one of the offered answers.")
            if session.status != "inProgress" or task.status in {"completed", "skipped"}:
                raise PracticeConflictError("This lesson is not active.")
            is_correct = _lesson_answer_is_correct(task, question_id, answer)
            attempts = list((stored or {}).get("attempts", []))
            attempts.append(
                {
                    "answer": answer,
                    "isCorrect": is_correct,
                    "assistance": list((stored or {}).get("assistance", [])),
                }
            )
            locked = is_correct or len(attempts) >= 3 or not question.allow_retry
            assistance = list((stored or {}).get("assistance", []))
            if question.allow_retry and not is_correct and len(attempts) >= 3:
                assistance.append("fullModel")
            task_checks[question_id] = {
                "answer": answer,
                "isCorrect": is_correct,
                "attempts": attempts,
                "assistance": assistance,
                "locked": locked,
            }
            checked = self._lesson_check(
                task, question_id, answer, is_correct, task_checks[question_id]
            )
            event = record_question(
                c,
                self.user_id,
                session,
                task,
                question_id,
                answer,
                is_correct,
                checked.outcome.model_dump(mode="json", by_alias=True),
            )
            task_checks[question_id]["basilEarned"] = event["basil_earned"]
            mission_checks[str(task.id)] = task_checks
            draft["missionChecks"] = mission_checks
            c.execute(
                update(sessions).where(sessions.c.id == session.id).values(analysis_draft=draft)
            )
            return self._lesson_check(
                task, question_id, answer, is_correct, task_checks[question_id]
            )

    def lesson_checks(self, task_id):
        """Restore checks already saved for a sequential grammar lesson."""
        with self.read_connection() as c:
            task = self._task_row(c, task_id)
            if task.kind != "grammarLesson":
                raise PracticeConflictError("This lesson does not support per-question checking.")
            session = self._session(c, task.session_id)
            task_checks = (
                (session.analysis_draft or {}).get("missionChecks", {}).get(str(task.id), {})
            )
            checks = []
            for question in task.public_content.questions:
                stored = task_checks.get(question.question_id)
                event = compatible_question(
                    question_event(c, self.user_id, task.id, question.question_id),
                    task, question.question_id,
                )
                if stored is None and event:
                    stored = {
                        "answer": event["answer"],
                        "isCorrect": event["is_correct"],
                        "locked": True,
                    }
                if stored is not None and event:
                    stored = {**stored, "basilEarned": event["basil_earned"]}
                if stored is not None and "answer" in stored:
                    checks.append(
                        self._lesson_check(
                            task,
                            question.question_id,
                            stored["answer"],
                            stored["isCorrect"],
                            stored,
                        )
                    )
            assistance_steps = {
                question_id: stored.get("assistance", [])
                for question_id, stored in task_checks.items()
                if stored.get("assistance")
            }
            return LessonChecksResponse(checks=checks, assistance_steps=assistance_steps)

    def lesson_assistance(self, task_id, question_id, step):
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            if task.kind != "grammarLesson" or task.public_content.mission_id != "M06":
                raise PracticeConflictError("This task does not support mission assistance.")
            session_row = (
                c.execute(
                    select(sessions)
                    .where(
                        sessions.c.id == task.session_id,
                        sessions.c.user_id == self.user_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if session_row is None:
                raise PracticeNotFoundError("Task not found.")
            session = parse_session(session_row)
            question = next(
                (item for item in task.public_content.questions if item.question_id == question_id),
                None,
            )
            if question is None or step not in (question.assistance_steps or []):
                raise PracticeConflictError("That assistance step is not available.")
            draft = dict(session.analysis_draft or {})
            checks = dict(draft.get("missionChecks") or {})
            task_checks = dict(checks.get(str(task.id)) or {})
            current = dict(task_checks.get(question_id) or {})
            if current.get("locked"):
                raise PracticeConflictError("This question is already locked.")
            used = list(current.get("assistance") or [])
            if (
                len(used) >= len(question.assistance_steps)
                or question.assistance_steps[len(used)] != step
            ):
                raise PracticeConflictError("Use the next assistance step in order.")
            current["assistance"] = [*used, step]
            task_checks[question_id] = current
            checks[str(task.id)] = task_checks
            draft["missionChecks"] = checks
            c.execute(
                update(sessions)
                .where(sessions.c.id == session.id)
                .values(
                    analysis_draft=draft,
                )
            )
            mission_state = task.answer_key.mission_state or {}
            private = mission_state.get("answers", {}).get(question_id, {})
            content = None
            if step == "replayAudio":
                content = question.audio_text or question.complete_chunk
            elif step == "visualDetail":
                transaction = mission_state.get("transaction", {})
                details = transaction.get("requestDetails", {})
                content = (
                    f"Order: {transaction.get('quantity')} {details.get('size') or ''} "
                    f"{transaction.get('itemLabel')}".strip()
                )
            elif step == "phraseOnset":
                content = next(iter(private.get("chunks") or ()), None)
                content = content or (private.get("model") or "").split(" ")[0]
            elif step == "chunkBank":
                content = " · ".join(
                    [*(private.get("chunks") or []), *question.token_bank[:1]]
                ) or " · ".join(option.label for option in question.options)
            else:
                content = private.get("model")
            return LessonAssistanceResponse(
                question_id=question_id,
                step=step,
                content=content or question.prompt,
            )

    def mission_scenario(self, task_id, action, scene_object_id=None):
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            if task.kind != "grammarLesson" or task.public_content.mission_id != "M06":
                raise PracticeConflictError("This task does not support mission scenarios.")
            session_row = (
                c.execute(
                    select(sessions)
                    .where(
                        sessions.c.id == task.session_id,
                        sessions.c.user_id == self.user_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if session_row is None:
                raise PracticeNotFoundError("Task not found.")
            session = parse_session(session_row)
            rows = (
                c.execute(
                    select(session_tasks)
                    .where(
                        session_tasks.c.session_id == session.id,
                        session_tasks.c.public_content["missionId"].astext == "M06",
                    )
                    .order_by(session_tasks.c.order_index)
                )
                .mappings()
                .all()
            )
            tasks = [SessionTask.model_validate(dict(row)) for row in rows]
            if len(tasks) != 2:
                raise PracticeConflictError("The M06 scenario is not available.")
            draft = dict(session.analysis_draft or {})
            if action == "accept":
                for current in tasks:
                    content = current.public_content.model_dump(mode="json", by_alias=True)
                    key = current.answer_key.model_dump(mode="json", by_alias=True)
                    state = key.setdefault("missionState", {})
                    state["scenarioAccepted"] = True
                    transaction = state.get("transaction", {})
                    transaction["scenarioAccepted"] = True
                    state["transaction"] = transaction
                    if content.get("scenario"):
                        content["scenario"]["accepted"] = True
                    c.execute(
                        update(session_tasks)
                        .where(session_tasks.c.id == current.id)
                        .values(public_content=content, answer_key=key)
                    )
                mission_plan = list(draft.get("missionPlan") or [])
                for entry in mission_plan:
                    if entry.get("missionId") == "M06":
                        entry["transaction"] = {
                            **tasks[0].answer_key.mission_state["transaction"],
                            "scenarioAccepted": True,
                        }
                draft["missionPlan"] = mission_plan
                c.execute(
                    update(sessions)
                    .where(sessions.c.id == session.id)
                    .values(
                        analysis_draft=draft,
                    )
                )
                changed = [
                    current.model_copy(
                        update={
                            "public_content": current.public_content.model_copy(
                                update={
                                    "scenario": current.public_content.scenario.model_copy(
                                        update={"accepted": True}
                                    )
                                    if current.public_content.scenario
                                    else None
                                }
                            ),
                        }
                    )
                    for current in tasks
                ]
            else:
                # Pack M06 lessons offer no alternative items, so there is none to switch to.
                raise PracticeConflictError("Choose one of the offered alternatives.")
            return MissionScenarioResponse(
                accepted=all(
                    task.public_content.scenario.accepted
                    for task in changed
                    if task.public_content.scenario
                )
                or action == "choose",
                tasks=[
                    SessionTaskPublic.from_internal(current, mode=session.mode)
                    for current in changed
                ],
            )

    def _scene_media(self, c, session):
        asset = MediaAsset.model_validate(
            dict(
                c.execute(
                    select(media_assets).where(media_assets.c.id == session.scene_media_asset_id)
                )
                .mappings()
                .one()
            )
        )
        scene = (
            c.execute(
                select(preloaded_scenes.c.slug, preloaded_scenes.c.title).where(
                    preloaded_scenes.c.media_asset_id == asset.id
                )
            )
            .mappings()
            .first()
            if asset.source == "preloaded"
            else None
        )
        return asset, scene

    def _scene_objects(self, c, session):
        draft = session.analysis_draft
        use_draft = bool(draft) and session.status in {
            "created",
            "analyzingScene",
            "awaitingObjectReview",
        }
        if use_draft:
            objects = [SceneObject.model_validate(obj) for obj in draft.get("objects", [])]
            relations = [
                SceneObjectRelation.model_validate(row) for row in draft.get("relations", [])
            ]
        else:
            objects = []
            relations = []
            seen_objects = set()
            for row in c.execute(
                select(
                    scene_objects,
                    *[column.label(f"r_{column.name}") for column in scene_object_relations.c],
                )
                .select_from(
                    scene_objects.outerjoin(
                        scene_object_relations,
                        scene_object_relations.c.subject_scene_object_id == scene_objects.c.id,
                    )
                )
                .where(scene_objects.c.session_id == session.id)
                .order_by(scene_objects.c.id)
            ).mappings():
                if row["id"] not in seen_objects:
                    seen_objects.add(row["id"])
                    objects.append(
                        SceneObject.model_validate({k: row[k] for k in SceneObject.model_fields})
                    )
                if row["r_id"] is not None:
                    relations.append(
                        SceneObjectRelation.model_validate(
                            {k: row[f"r_{k}"] for k in SceneObjectRelation.model_fields}
                        )
                    )
        return objects, relations

    def _vocabulary(self, c, session, objects):
        ids = [o.vocabulary_item_id for o in objects if o.vocabulary_item_id]
        words = []
        translations = []
        if ids:
            source = (
                select(language_profiles.c.source_language_code)
                .where(language_profiles.c.id == session.language_profile_id)
                .scalar_subquery()
            )
            seen = set()
            for row in c.execute(
                select(
                    vocabulary_items,
                    *[column.label(f"t_{column.name}") for column in vocabulary_translations.c],
                )
                .select_from(
                    vocabulary_items.outerjoin(
                        vocabulary_translations,
                        and_(
                            vocabulary_translations.c.vocabulary_item_id == vocabulary_items.c.id,
                            func.lower(vocabulary_translations.c.source_language_code)
                            == func.lower(source),
                        ),
                    )
                )
                .where(vocabulary_items.c.id.in_(ids))
            ).mappings():
                if row["id"] not in seen:
                    seen.add(row["id"])
                    words.append(
                        VocabularyItem.model_validate(
                            {k: row[k] for k in VocabularyItem.model_fields}
                        )
                    )
                if row["t_id"] is not None:
                    translations.append(
                        VocabularyTranslation.model_validate(
                            {k: row[f"t_{k}"] for k in VocabularyTranslation.model_fields}
                        )
                    )
        return words, translations

    def _detail(self, c, session, *, active_session_count=0):
        asset, scene = self._scene_media(c, session)
        objects, relations = self._scene_objects(c, session)
        words, translations = self._vocabulary(c, session, objects)
        draft = session.analysis_draft
        object_ids = {str(item.id) for item in objects}
        action_suggestions = [
            suggestion
            for suggestion in (draft or {}).get("actionSuggestions", [])
            if set(suggestion.get("sceneObjectIds", [])) <= object_ids
        ]
        price_suggestions = [
            suggestion
            for suggestion in (draft or {}).get("priceSuggestions", [])
            if suggestion.get("sceneObjectId") in object_ids
        ]
        tasks = self._tasks(c, session.id)
        return SessionDetailResponse(
            scene_analysis_progress=(
                {
                    "stage": "ready" if session.status == "awaitingObjectReview"
                    else draft["analysisStage"],
                    "startedAt": (draft or {}).get("processingStartedAt"),
                }
                if session.status == "awaitingObjectReview"
                or (session.status == "analyzingScene" and (draft or {}).get("analysisStage"))
                else None
            ),
            session=session,
            media_asset=asset,
            scene_id=scene["slug"] if scene else None,
            title=_scene_title(session, scene),
            analysis_mode=None if asset.source == "preloaded" else "placeholder",
            scene_objects=objects,
            scene_object_relations=relations,
            scene_action_suggestions=action_suggestions,
            scene_price_suggestions=price_suggestions,
            vocabulary=words,
            translations=translations,
            translation_preview=(draft or {}).get("translationPreview"),
            analysis_retryable=analysis_retryable(session),
            personalization=(draft or {}).get("personalization"),
            counted_groups=saved_counted_groups(draft),
            mission_guidance=(draft or {}).get("missionGuidance", []),
            scene_shortfall=(
                (draft or {}).get("sceneShortfall")
                if session.status in _REVIEW_STATUSES
                else None
            ),
            mission_choices=(draft or {}).get("missionChoices"),
            review_markers=(
                {} if session.status in _REVIEW_STATUSES
                else (draft or {}).get("reviewMarkers") or {}
            ),
            provisional_mission_plan=(draft or {}).get("provisionalMissionPlan", []),
            suggested_scene_object_ids=(draft or {}).get("suggestedSceneObjectIds", []),
            tasks=[SessionTaskPublic.from_internal(t, mode=session.mode) for t in tasks],
            progress=task_progress(tasks),
            next_task_id=next(
                (t.id for t in tasks if t.status not in {"completed", "skipped"}), None
            ),
            active_session_count=active_session_count,
        )

    def _active_row(self, c, profile_id, mode):
        return (
            c.execute(
                select(
                    sessions,
                    _stale_processing().label("is_stale"),
                    func.count().over().label("active_session_count"),
                )
                .where(
                    sessions.c.user_id == self.user_id,
                    sessions.c.language_profile_id == profile_id,
                    sessions.c.mode == mode,
                    sessions.c.status.not_in(TERMINAL),
                )
                .order_by(sessions.c.started_at.desc().nulls_last(), sessions.c.id)
            )
            .mappings()
            .first()
        )

    def get(self, session_id, profile_id=None):
        with self.read_connection() as c:
            session = self._session(c, session_id, profile_id)
            if session.status not in PROCESSING_STATUSES:
                return self._detail(c, session)
            stale = c.execute(
                select(_stale_processing()).select_from(sessions).where(sessions.c.id == session.id)
            ).scalar_one()
            if not stale:
                return self._detail(c, session)
        # Only an expired processing session needs the write path.
        with self.transaction() as c:
            self._expire_stale(
                c,
                sessions.c.id == session_id,
                sessions.c.user_id == self.user_id,
            )
            return self._detail(c, self._session(c, session_id, profile_id))

    def active(self, profile_id, mode=SessionMode.LESSON):
        try:
            with self.read_connection() as c:
                if (
                    c.execute(
                        select(users.c.id).where(users.c.id == self.user_id)
                    ).scalar_one_or_none()
                    is None
                ):
                    return None
                row = self._active_row(c, profile_id, mode)
                if row is None:
                    return None
                if not row["is_stale"]:
                    return self._detail(
                        c,
                        parse_session(row),
                        active_session_count=row["active_session_count"],
                    )
            # Only an expired processing session needs the write path.
            with self.transaction() as c:
                self._reap(c, profile_id)
                row = self._active_row(c, profile_id, mode)
                return (
                    self._detail(
                        c,
                        parse_session(row),
                        active_session_count=row["active_session_count"],
                    )
                    if row
                    else None
                )
        except PracticeNotFoundError:
            return None

    def _practice_media(self, c, profile_id, asset_id):
        """The active profile and an image this user may practise with."""
        profile = (
            c.execute(
                select(language_profiles).where(
                    language_profiles.c.id == profile_id,
                    language_profiles.c.user_id == self.user_id,
                    language_profiles.c.is_active.is_(True),
                )
            )
            .mappings()
            .one_or_none()
        )
        if profile is None:
            raise PracticeConflictError("Select the active language profile.")
        asset = (
            c.execute(select(media_assets).where(media_assets.c.id == asset_id))
            .mappings()
            .one_or_none()
        )
        if (
            not asset
            or asset["media_type"] != "image"
            or not (
                (asset["source"] == "preloaded" and asset["owner_user_id"] is None)
                or (
                    asset["source"] in {"camera", "userUpload"}
                    and asset["owner_user_id"] == self.user_id
                )
            )
        ):
            raise PracticeNotFoundError("Image not found.")
        if (
            asset["source"] == "preloaded"
            and c.execute(
                select(preloaded_scenes.c.id).where(
                    preloaded_scenes.c.media_asset_id == asset["id"],
                    preloaded_scenes.c.is_active.is_(True),
                )
            ).first()
            is None
        ):
            raise PracticeNotFoundError("Scene not found.")
        return profile, asset

    def create(self, request):
        with self.transaction() as c:
            _profile, asset = self._practice_media(
                c, request.language_profile_id, request.media_asset_id
            )

            def tagged(session):
                if request.daily_challenge_day is not None:
                    enter_challenge(
                        c, self.user_id, session.id, request.daily_challenge_day, asset["source"]
                    )
                return self._detail(c, session)

            if request.idempotency_key:
                existing = (
                    c.execute(
                        select(sessions).where(
                            sessions.c.user_id == self.user_id,
                            sessions.c.language_profile_id == request.language_profile_id,
                            sessions.c.idempotency_key == request.idempotency_key,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing:
                    if (
                        existing["scene_media_asset_id"] != request.media_asset_id
                        or existing["mode"] != SessionMode.LESSON
                    ):
                        raise PracticeConflictError("This request key was used for another image.")
                    return tagged(parse_session(existing))
            self._reap(c, request.language_profile_id)
            # Re-selecting an image resumes its unfinished session, but an
            # unfinished session for another image must never block a learner
            # from starting a new one.
            existing = (
                c.execute(
                    select(sessions)
                    .where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.language_profile_id == request.language_profile_id,
                        sessions.c.scene_media_asset_id == request.media_asset_id,
                        sessions.c.mode == SessionMode.LESSON,
                        sessions.c.status.not_in(TERMINAL),
                    )
                    .order_by(sessions.c.started_at.desc().nulls_last(), sessions.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return tagged(parse_session(existing))
            self._check_daily_tier_limit(c)
            self._check_active_limit(c, request.language_profile_id)
            self._check_lesson_language(_profile)
            session = Session(
                user_id=self.user_id,
                language_profile_id=request.language_profile_id,
                scene_media_asset_id=request.media_asset_id,
                idempotency_key=request.idempotency_key,
            )
            c.execute(insert(sessions).values(**session.model_dump(by_alias=False)))
            return tagged(session)

    @staticmethod
    def _check_lesson_language(profile):
        """Lessons come only from language packs: refuse one before it starts, not mid-way."""
        from app.language_packs.context import operation_context

        if operation_context(SessionMode.LESSON, dict(profile)) is None:
            raise LessonLanguageUnavailableError(
                "Photo lessons aren't available for this language yet."
            )

    def _check_daily_tier_limit(self, c):
        user_row = (
            c.execute(
                select(users.c.tier, users.c.timezone).where(users.c.id == self.user_id)
            )
            .mappings()
            .one_or_none()
        )
        if not user_row:
            return
        tier_val = user_row.get("tier", "beta")
        if tier_val == "beta" or tier_val == AccountTier.BETA.value:
            return
        if tier_val in ("free", AccountTier.FREE.value):
            limit = 1
        elif tier_val in ("plus", AccountTier.PLUS.value):
            limit = 10
        else:
            return

        tz_str = user_row.get("timezone") or "UTC"
        try:
            user_tz = ZoneInfo(tz_str)
        except Exception:
            user_tz = ZoneInfo("UTC")

        now_user = datetime.now(user_tz)
        today_start = datetime(now_user.year, now_user.month, now_user.day, tzinfo=user_tz)

        count = c.execute(
            select(func.count()).select_from(sessions).where(
                sessions.c.user_id == self.user_id,
                sessions.c.mode == SessionMode.LESSON,
                sessions.c.created_at >= today_start,
            )
        ).scalar_one()

        if count >= limit:
            tier_label = "Free" if limit == 1 else "Plus"
            plural = "s" if limit > 1 else ""
            upgrade_msg = " Upgrade to Plus for 10 lessons per day." if limit == 1 else ""
            raise DailyLessonLimitReachedError(
                f"{tier_label} tier is limited to {limit} photo lesson{plural} per day."
                f"{upgrade_msg}"
            )

    def _check_active_limit(self, c, profile_id, mode=SessionMode.LESSON):
        active_count = c.execute(
            select(func.count()).select_from(sessions).where(
                sessions.c.user_id == self.user_id,
                sessions.c.language_profile_id == profile_id,
                sessions.c.mode == mode,
                sessions.c.status.not_in(TERMINAL),
            )
        ).scalar_one()
        if active_count >= MAX_ACTIVE_SESSIONS:
            raise ActiveSessionLimitReachedError(
                "You can keep up to three unfinished practices open at once. "
                "Finish or leave one before starting another."
            )

    def _expire_stale(self, c, *scope):
        """Fail stale processing sessions inside `scope` with their status's code."""
        for status, failure_code in PROCESSING_FAILURE_CODES.items():
            stale = c.execute(select(sessions).where(*scope, _stale_processing(status))).mappings()
            for row in stale:
                self._transition(c, parse_session(row), "failed", failure_code=failure_code)

    def _reap(self, c, profile_id):
        """Expire stale non-terminal sessions so a crashed request cannot block a new run."""
        self._expire_stale(
            c,
            sessions.c.user_id == self.user_id,
            sessions.c.language_profile_id == profile_id,
        )

    def analyze(self, session_id, profile_id):
        with self.transaction() as c:
            session = self._session(c, session_id, profile_id)
            if session.mode == SessionMode.ISPY:
                raise PracticeConflictError("I-Spy games reuse a confirmed scene.")
            if session.status in TERMINAL:
                raise PracticeConflictError("Cannot analyze a terminal session.")
            if session.status in {"ready", "inProgress"}:
                raise PracticeConflictError("Session analysis is already finished.")
            if session.status != "created":
                # analyzingScene/awaitingObjectReview/generatingTasks: never re-run the model.
                return self._detail(c, session)
            inputs = self._analysis_inputs(c, session)
            asset, profile, scene = inputs
            cached = (
                c.execute(
                    select(media_scene_analyses).where(
                        media_scene_analyses.c.media_asset_id == asset.id,
                        media_scene_analyses.c.prompt_version
                        == SCENE_ANALYSIS_PROMPT_VERSION,
                        media_scene_analyses.c.schema_version
                        == SCENE_ANALYSIS_SCHEMA_VERSION,
                    )
                )
                .mappings()
                .one_or_none()
                if asset.source in {"camera", "userUpload"}
                else None
            )
            claimed = self._transition(
                c, session, "analyzingScene", analysis_draft={"analysisAttempts": 1}
            )
            if cached is not None:
                result = scene_result_from_inventory(claimed, cached["inventory"])
                focused = self._analysis_draft(claimed, profile, result)
                return self._detail(
                    c,
                    self._transition(
                        c,
                        claimed,
                        "awaitingObjectReview",
                        session_title=result.title,
                        session_summary=result.summary,
                        analysis_draft=focused,
                    ),
                )
            detail = self._detail(c, claimed)
        return self._start_analysis(
            session_id, profile_id, claimed, detail, asset, profile, scene
        )

    def retry_analysis(self, session_id, profile_id):
        """Rerun a temporarily failed analysis on the session's saved image."""
        with self.transaction() as c:
            session = self._session(c, session_id, profile_id)
            if session.status in {"analyzingScene", "awaitingObjectReview"}:
                # A concurrent retry already claimed the session.
                return self._detail(c, session)
            if not analysis_retryable(session):
                raise PracticeConflictError("This practice cannot retry its scene analysis.")
            self._check_active_limit(c, profile_id)
            if c.execute(
                select(sessions.c.id).where(
                    sessions.c.user_id == self.user_id,
                    sessions.c.language_profile_id == profile_id,
                    sessions.c.scene_media_asset_id == session.scene_media_asset_id,
                    sessions.c.mode == SessionMode.LESSON,
                    sessions.c.status.not_in(TERMINAL),
                )
            ).first():
                raise PracticeConflictError("This photo already has an open practice.")
            inputs = self._analysis_inputs(c, session)
            claimed = self._transition(
                c,
                session,
                "analyzingScene",
                failure_code=None,
                analysis_draft={"analysisAttempts": analysis_attempts(session) + 1},
            )
            detail = self._detail(c, claimed)
        return self._start_analysis(session_id, profile_id, claimed, detail, *inputs)

    def _analysis_inputs(self, c, session):
        asset = MediaAsset.model_validate(
            dict(
                c.execute(
                    select(media_assets).where(
                        media_assets.c.id == session.scene_media_asset_id
                    )
                )
                .mappings()
                .one()
            )
        )
        profile = (
            c.execute(
                select(language_profiles).where(
                    language_profiles.c.id == session.language_profile_id
                )
            )
            .mappings()
            .one()
        )
        scene = (
            c.execute(
                select(preloaded_scenes).where(preloaded_scenes.c.media_asset_id == asset.id)
            )
            .mappings()
            .first()
            if asset.source == "preloaded"
            else None
        )
        if asset.source == "preloaded" and scene is None:
            raise PracticeNotFoundError("Curated scene not found.")
        return asset, dict(profile), dict(scene) if scene else None

    def _start_analysis(self, session_id, profile_id, claimed, detail, asset, profile, scene):
        if asset.source == "preloaded":
            # Curated scenes already have their objects, marker positions,
            # attributes and relations saved. Set up the fresh learner session
            # on this request instead of showing the uploaded-photo animation.
            self._run_scene_analysis(session_id, profile_id, claimed, asset, profile, scene)
            return self.get(session_id, profile_id)
        self.background.submit(
            self._run_scene_analysis, session_id, profile_id, claimed, asset, profile, scene
        )
        return detail

    def _record_analysis_stage(self, claimed, stage):
        """Publish a milestone only for the still-current attempt, in a short transaction."""
        try:
            with self.transaction() as c:
                c.execute(
                    update(sessions)
                    .where(
                        sessions.c.id == claimed.id,
                        sessions.c.user_id == self.user_id,
                        sessions.c.status == "analyzingScene",
                        sessions.c.analysis_draft["processingStartedAt"].astext
                        == (claimed.analysis_draft or {}).get("processingStartedAt"),
                    )
                    .values(
                        analysis_draft=sessions.c.analysis_draft.op("||")({"analysisStage": stage})
                    )
                )
        except PracticeStorageError:
            # Progress is advisory; a missed update must not discard a valid analysis.
            logger.warning("Could not publish scene-analysis progress for %s.", claimed.id)

    def _run_scene_analysis(self, session_id, profile_id, claimed, asset, profile, scene):
        """Model round-trip, off the request path. Must never raise to its runner."""
        try:
            progressive = getattr(self.analyzer, "analyze_with_progress", None)
            if progressive is not None:
                result = progressive(
                    claimed, asset, profile, scene,
                    partial(self._record_analysis_stage, claimed),
                )
            else:
                result = self.analyzer.analyze(claimed, asset, profile, scene)
            self._record_analysis_stage(claimed, "savingResults")
            if asset.source in {"camera", "userUpload"}:
                result = result.model_copy(update={"title": uploaded_scene_title(result)})
            with self.transaction() as c:
                current = self._session(c, session_id, profile_id)
                if current.status != "analyzingScene":
                    return
                if asset.source in {"camera", "userUpload"}:
                    if result.content_hash:
                        c.execute(
                            upsert(photo_identities)
                            .values(
                                media_asset_id=asset.id,
                                user_id=self.user_id,
                                content_hash=result.content_hash,
                                created_at=utc_now(),
                            )
                            .on_conflict_do_nothing()
                        )
                    inventory = scene_inventory(result)
                    now = utc_now()
                    c.execute(
                        upsert(media_scene_analyses)
                        .values(
                            media_asset_id=asset.id,
                            prompt_version=SCENE_ANALYSIS_PROMPT_VERSION,
                            schema_version=SCENE_ANALYSIS_SCHEMA_VERSION,
                            inventory=inventory,
                            created_at=now,
                            updated_at=now,
                        )
                        .on_conflict_do_update(
                            index_elements=["media_asset_id"],
                            set_={
                                "prompt_version": SCENE_ANALYSIS_PROMPT_VERSION,
                                "schema_version": SCENE_ANALYSIS_SCHEMA_VERSION,
                                "inventory": inventory,
                                "updated_at": now,
                            },
                        )
                    )
                self._transition(
                    c,
                    current,
                    "awaitingObjectReview",
                    session_title=result.title,
                    session_summary=result.summary,
                    analysis_draft=self._analysis_draft(current, profile, result),
                )
        except Exception as error:
            error_code = getattr(error, "code", None)
            logger.exception(
                "Scene analysis failed for session %s (code=%s).",
                session_id,
                error_code or "unknown",
            )
            try:
                # Compare by value: the enum is a StrEnum and importing the
                # scene-analysis feature here would create an import cycle.
                failure_code = (
                    "imageModerationFailed"
                    if error_code == "imageModerationFailed"
                    else "sceneAnalysisFailed"
                )

                with self.transaction() as c:
                    current = self._session(c, session_id)
                    if current.status == "analyzingScene":
                        self._transition(c, current, "failed", failure_code=failure_code)
            except Exception:
                logger.exception(
                    "Could not record the analysis failure for session %s.", session_id
                )

    @staticmethod
    def _analysis_draft(session, profile, result):
        from app.language_packs.context import operation_context

        context = operation_context(session.mode, profile)
        candidates = lesson_missions(session.mode, profile, context)
        provisional, selected_ids = provisional_mission_focus(
            candidates, result.objects, result.relations, context
        )
        return {
            "analysisAttempts": analysis_attempts(session),
            "processingStartedAt": (session.analysis_draft or {}).get("processingStartedAt"),
            **({"languageContext": context.snapshot()} if context else {}),
            "objects": [
                obj.model_dump(mode="json", by_alias=False) for obj in result.objects
            ],
            "relations": [
                row.model_dump(mode="json", by_alias=False) for row in result.relations
            ],
            "actionSuggestions": [
                row.model_dump(mode="json", by_alias=True)
                for row in result.action_suggestions
            ],
            "priceSuggestions": [
                row.model_dump(mode="json", by_alias=True)
                for row in result.price_suggestions
            ],
            "provisionalMissionPlan": [mission_snapshot(item) for item in provisional],
            "suggestedSceneObjectIds": [str(item) for item in selected_ids],
        }

    def _catalog_word(self, c, profile, label):
        match = (
            c.execute(
                select(vocabulary_items, vocabulary_translations.c.translated_text)
                .join(
                    vocabulary_translations,
                    vocabulary_translations.c.vocabulary_item_id == vocabulary_items.c.id,
                )
                .where(
                    func.lower(vocabulary_items.c.language_code)
                    == profile["target_language_code"].lower(),
                    func.lower(vocabulary_translations.c.source_language_code)
                    == profile["source_language_code"].lower(),
                    func.lower(vocabulary_translations.c.translated_text) == label.strip().lower(),
                )
                .order_by(vocabulary_items.c.id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if not match:
            raise PracticeConflictError(
                f'"{label}" is not in the vocabulary for your learning language yet. '
                "Please choose another word."
            )
        return VocabularyItem.model_validate(
            {key: match[key] for key in VocabularyItem.model_fields}
        )

    def check_word(self, session_id, profile_id, label):
        with self.engine.connect() as c:
            session = self._session(c, session_id, profile_id)
            profile = (
                c.execute(select(language_profiles).where(language_profiles.c.id == profile_id))
                .mappings()
                .one()
            )
            if self.translator:
                context = session_language_context(session, profile)
                if context is not None:
                    # Available to confirm as a scene candidate, not translated or
                    # linguistically ready. The checkpoint validates translation later.
                    return {"available": True, "translationReady": False}
            self._catalog_word(c, profile, label)
            return {"available": True}

    def review(self, session_id, profile_id, request):
        detail = self._review(session_id, profile_id, request)
        self.background.submit(self._run_task_generation, session_id, profile_id)
        return detail

    def _run_task_generation(self, session_id, profile_id, generate=None):
        """Translator + lesson generation, off the request path. Never re-raises."""
        revision = None
        try:
            claim = self._claim_generation(session_id, profile_id)
            if claim is None:
                return
            revision = claim.revision
            (generate or self._generate_tasks)(claim)
        except Exception:
            logger.exception("Task generation failed for session %s.", session_id)
            try:
                with self.transaction() as c:
                    current = self._session(c, session_id)
                    # A newer claim owns the session, so this failure is stale.
                    if current.status not in TERMINAL and revision in (
                        None, self._generation_revision(c, session_id)
                    ):
                        self._transition(
                            c, current, "failed", failure_code="taskGenerationFailed"
                        )
            except Exception:
                logger.exception(
                    "Could not record the task generation failure for session %s.",
                    session_id,
                )

    def _review(self, session_id, profile_id, request):
        with self.transaction() as c:
            session = self._session(c, session_id, profile_id)
            if session.mode == SessionMode.ISPY:
                raise PracticeConflictError("I-Spy games reuse a confirmed scene.")
            if session.status == "generatingTasks":
                raise PracticeConflictError("The confirmed scene is already generating tasks.")
            if session.status in TERMINAL:
                raise PracticeConflictError("This session cannot be edited.")
            tasks = self._tasks(c, session_id)
            if (
                any(task.status != "pending" for task in tasks)
                or c.execute(
                    select(task_attempts.c.id)
                    .join(session_tasks, session_tasks.c.id == task_attempts.c.session_task_id)
                    .where(session_tasks.c.session_id == session_id)
                    .limit(1)
                ).first()
            ):
                raise PracticeConflictError(
                    "Practice has started. Start a new session to change its words."
                )
            detail = self._detail(c, session)
            existing = {obj.id: obj for obj in detail.scene_objects}
            if any(object_id not in existing for object_id in request.accepted_object_ids):
                raise PracticeConflictError("An object does not belong to this session.")
            if any(item.id not in existing for item in request.repositioned_objects):
                raise PracticeConflictError("A marker does not belong to this session.")
            if request.scene_title is not None:
                c.execute(
                    update(sessions)
                    .where(sessions.c.id == session_id)
                    .values(session_title=request.scene_title)
                )
                session = session.model_copy(update={"session_title": request.scene_title})
            profile = (
                c.execute(select(language_profiles).where(language_profiles.c.id == profile_id))
                .mappings()
                .one()
            )
            confirmed = []
            positions = {item.id: item.anchor_point for item in request.repositioned_objects}
            for object_id in request.accepted_object_ids:
                obj = existing[object_id].model_copy(
                    update={
                        "attributes": request.object_attributes.get(object_id) or None,
                        "anchor_point": positions.get(object_id, existing[object_id].anchor_point),
                    }
                )
                confirmed.append(obj)
                values = object_values(obj)
                c.execute(
                    upsert(scene_objects)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={key: value for key, value in values.items() if key != "id"},
                    )
                )
            for added in request.added_objects:
                # Scope client-generated IDs to this session; retries keep the same object.
                object_id = uuid5(session_id, "manual:" + str(added.id))
                obj = SceneObject(
                    id=object_id,
                    session_id=session_id,
                    label=added.label,
                    # With a translator, new labels are linked after translation.
                    # Offline practice reuses an existing catalogue translation.
                    vocabulary_item_id=(
                        None if self.translator else self._catalog_word(c, profile, added.label).id
                    ),
                    anchor_point={"x": added.x, "y": added.y},
                    attributes=request.object_attributes.get(added.id) or None,
                )
                confirmed.append(obj)
                values = object_values(obj)
                c.execute(
                    upsert(scene_objects)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={key: value for key, value in values.items() if key != "id"},
                    )
                )
            accepted = set(request.accepted_object_ids) | {
                uuid5(session_id, "manual:" + str(added.id)) for added in request.added_objects
            }
            c.execute(delete(session_tasks).where(session_tasks.c.session_id == session_id))
            c.execute(
                delete(scene_objects).where(
                    scene_objects.c.session_id == session_id, scene_objects.c.id.not_in(accepted)
                )
            )
            c.execute(
                delete(scene_object_relations).where(
                    scene_object_relations.c.subject_scene_object_id.in_(
                        select(scene_objects.c.id).where(scene_objects.c.session_id == session_id)
                    )
                )
            )
            manual_ids = {
                item.id: uuid5(session_id, "manual:" + str(item.id))
                for item in request.added_objects
            }
            mission_choices = None
            if request.mission_choices is not None:
                mission_choices = request.mission_choices.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
                ownership = mission_choices.get("ownership")
                if ownership:
                    object_id = UUID(ownership["sceneObjectId"])
                    ownership["sceneObjectId"] = str(manual_ids.get(object_id, object_id))
                preference = mission_choices.get("preference")
                if preference:
                    preference["sceneObjectIds"] = [
                        str(manual_ids.get(UUID(value), UUID(value)))
                        for value in preference["sceneObjectIds"]
                    ]
                    if preference.get("chosenObjectId"):
                        object_id = UUID(preference["chosenObjectId"])
                        preference["chosenObjectId"] = str(
                            manual_ids.get(object_id, object_id)
                        )
                    elif len(preference["sceneObjectIds"]) == 2:
                        preference["reaction"] = preference.get("reaction") or "like"
            draft = dict(c.execute(select(sessions.c.analysis_draft).where(
                sessions.c.id == session_id,
            )).scalar_one() or {})
            if mission_choices is None:
                draft.pop("missionChoices", None)
            else:
                draft["missionChoices"] = mission_choices
            c.execute(update(sessions).where(sessions.c.id == session_id).values(
                analysis_draft=draft,
            ))
            original_relations = {row.id: row for row in detail.scene_object_relations}
            for relation in request.relations:
                original = original_relations.get(relation.id)
                # Provenance is preserved only for unchanged server-generated suggestions.
                source_key = (
                    original.source_relation_key
                    if original
                    and (
                        original.subject_scene_object_id == relation.subject_scene_object_id
                        and original.reference_scene_object_id == relation.reference_scene_object_id
                        and original.relation == relation.relation
                    )
                    else None
                )
                c.execute(
                    insert(scene_object_relations).values(
                        id=relation.id
                        if original
                        else uuid5(session_id, "relation:" + str(relation.id)),
                        subject_scene_object_id=manual_ids.get(
                            relation.subject_scene_object_id, relation.subject_scene_object_id
                        ),
                        reference_scene_object_id=manual_ids.get(
                            relation.reference_scene_object_id, relation.reference_scene_object_id
                        ),
                        relation=relation.relation,
                        source_relation_key=source_key,
                    )
                )
            counted = self._save_counted_groups(
                c, session_id, request, confirmed, existing, manual_ids
            )
            self._save_review_markers(c, session_id, request, manual_ids)
            shortfall = self._plan_missions(c, session, profile, confirmed, counted, [
                relation.model_copy(update=dict(
                    subject_scene_object_id=manual_ids.get(
                        relation.subject_scene_object_id, relation.subject_scene_object_id
                    ),
                    reference_scene_object_id=manual_ids.get(
                        relation.reference_scene_object_id, relation.reference_scene_object_id
                    ),
                ))
                    for relation in request.relations
                ], mission_choices=mission_choices or {})
            if shortfall is not None:
                # Roll the review back so the learner can add facts; no lesson
                # without checkable missions is generated.
                raise InsufficientSceneError(shortfall)
            c.execute(
                update(sessions)
                .where(sessions.c.id == session_id)
                .values(scene_confirmed_at=utc_now())
            )
            session = self._session(c, session_id, profile_id)
            if session.status not in {"ready", "inProgress"}:
                session = self._transition(c, session, "generatingTasks")
            return self._detail(c, session)

    def _generation_revision(self, c, session_id):
        return c.execute(
            select(sessions.c.generation_revision).where(sessions.c.id == session_id)
        ).scalar_one()

    def _claim_generation(self, session_id, profile_id):
        """Claim the next generation revision and snapshot what the model calls need."""
        with self.transaction() as c:
            session = self._session(c, session_id, profile_id)
            if session.status in TERMINAL:
                return None
            revision = c.execute(
                update(sessions)
                .where(sessions.c.id == session_id)
                .values(generation_revision=sessions.c.generation_revision + 1)
                .returning(sessions.c.generation_revision)
            ).scalar_one()
            profile = (
                c.execute(select(language_profiles).where(language_profiles.c.id == profile_id))
                .mappings()
                .one()
            )
            language_context = session_language_context(session, profile)
            asset, scene = self._scene_media(c, session)
            objects, relations = self._scene_objects(c, session)
            history = None
            if (session.mode == SessionMode.LESSON
                    and os.getenv("LEARNER_MEMORY_ENABLED", "false").strip().lower() == "true"):
                labels = [obj.label for obj in objects]
                labels.extend(value for obj in objects for value in (obj.attributes or {}).values()
                              if isinstance(value, str))
                labels.extend(row.relation for row in relations)
                history = snapshot_learner_history(
                    c, self.user_id, dict(profile), session_id, labels,
                )
            if (
                "missionPlan" not in (session.analysis_draft or {})
                and lesson_missions(session.mode, dict(profile), language_context)
            ):
                self._plan_missions(
                    c,
                    session,
                    dict(profile),
                    objects,
                    saved_counted_groups(session.analysis_draft),
                    relations,
                    mission_choices=(session.analysis_draft or {}).get("missionChoices") or {},
                    language_context=language_context,
                )
                session = self._session(c, session_id, profile_id)
            missions = tuple(self._planned_missions(session, dict(profile), language_context))
            blocked = next((
                lesson_mission(m) for m in missions
                if language_context is not None
                and language_context.owns(lesson_mission(m).mission_id)
                and not language_context.is_ready(lesson_mission(m))
            ), None)
            if blocked is not None:
                raise LearningTaskGenerationError(
                    f"Selected {blocked.mission_id} level is not ready in this context"
                )
            draft = session.analysis_draft or {}
            mission_progress = (
                self._mission_progress(c, dict(profile), history) if missions else None
            )
            if mission_progress is not None:
                planned_m06 = next(
                    (
                        item
                        for item in draft.get("missionPlan", [])
                        if item.get("missionId") == "M06" and item.get("transaction")
                    ),
                    None,
                )
                if planned_m06:
                    mission_progress["m06Transaction"] = planned_m06["transaction"]
            return GenerationClaim(
                session_id,
                profile_id,
                revision,
                session,
                dict(profile),
                _scene_title(session, scene),
                objects,
                relations,
                *self._reuse(c, session, asset, objects, relations),
                learner_history=history,
                missions=missions,
                counted_groups=tuple(saved_counted_groups(session.analysis_draft)),
                mission_progress=mission_progress,
                roleplay_facts={
                    item["missionId"]: item["roleplayFacts"]
                    for item in draft.get("missionPlan", [])
                    if item.get("practiceLevel") == "A1" and "roleplayFacts" in item
                },
                learner_facts={
                    item["missionId"]: item["learnerFacts"]
                    for item in draft.get("missionPlan", [])
                    if item.get("practiceLevel") == "A0" and "learnerFacts" in item
                },
                review_markers=draft.get("reviewMarkers") or {},
                language_context=language_context,
            )

    def _mission_progress(self, c, profile, history):
        """Existing word progress in the target language, and term results from history.

        Colours and position phrases have no word-progress rows, so their familiarity
        comes only from the learner-history snapshot; without one they count as unseen.
        """
        rows = c.execute(
            select(
                vocabulary_items.c.id, vocabulary_items.c.display_text,
                vocabulary_items.c.gender, vocabulary_items.c.part_of_speech,
                user_vocabulary_progress.c.mastery_score,
            )
            .join(
                user_vocabulary_progress,
                user_vocabulary_progress.c.vocabulary_item_id == vocabulary_items.c.id,
            )
            .where(
                user_vocabulary_progress.c.user_id == self.user_id,
                func.lower(vocabulary_items.c.language_code)
                == profile["target_language_code"].lower(),
            )
            .order_by(vocabulary_items.c.display_text, vocabulary_items.c.id)
        ).mappings().all()
        terms = {}
        for word in (history or {}).get("words", []):
            total = word.get("correctCount", 0) + word.get("incorrectCount", 0)
            if word.get("term") and total:
                terms[fold(word["term"])] = word["correctCount"] / total
        # Plural forms count as taught once the learner completed a counting lesson.
        plurals_taught = c.execute(
            select(session_tasks.c.id)
            .join(sessions, sessions.c.id == session_tasks.c.session_id)
            .where(
                sessions.c.user_id == self.user_id,
                sessions.c.language_profile_id == profile["id"],
                session_tasks.c.status == "completed",
                session_tasks.c.public_content["missionId"].astext == "M03",
            )
            .limit(1)
        ).first() is not None
        m06_sessions = set()
        independent_q5 = set()
        if str(profile["proficiency_level"]).upper() == "A2" and str(
            profile["target_language_code"]
        ).lower() in {"es", "fr", "de", "ko"}:
            m06_rows = (
                c.execute(
                    select(
                        sessions.c.id.label("session_id"),
                        sessions.c.analysis_draft,
                        session_tasks.c.id.label("task_id"),
                    )
                    .join(session_tasks, session_tasks.c.session_id == sessions.c.id)
                    .where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.language_profile_id == profile["id"],
                        sessions.c.mode == SessionMode.LESSON,
                        sessions.c.status == "completed",
                        session_tasks.c.status == "completed",
                        session_tasks.c.public_content["missionId"].astext == "M06",
                        session_tasks.c.public_content["practiceLevel"].astext == "A2",
                    )
                )
                .mappings()
                .all()
            )
            for row in m06_rows:
                session_key = str(row["session_id"])
                m06_sessions.add(session_key)
                checks = (
                    (row["analysis_draft"] or {})
                    .get("missionChecks", {})
                    .get(str(row["task_id"]), {})
                    .get("m06-q5")
                )
                if checks and checks.get("isCorrect") and not checks.get("assistance"):
                    independent_q5.add(session_key)
        return dict(
            plurals_taught=plurals_taught,
            objects={str(row["id"]): float(row["mastery_score"]) for row in rows},
            m06CompletedLessons=len(m06_sessions),
            m06IndependentQ5=len(independent_q5),
            taught_nouns=[
                dict(text=row["display_text"], gender=row["gender"])
                for row in rows
                if row["part_of_speech"] == "noun" and row["gender"]
            ],
            terms=terms,
        )

    def _save_counted_groups(self, c, session_id, request, confirmed, existing, manual_ids):
        """Save the learner's counts, one per group of same-named confirmed objects."""
        by_id = {obj.id: obj for obj in confirmed}
        groups = {}
        for object_id, quantity in request.object_counts.items():
            obj = by_id[manual_ids.get(object_id, object_id)]
            label = obj.label.strip().casefold()
            if label in groups:
                raise PracticeConflictError("Count each group of matching objects once.")
            original = existing.get(object_id)
            suggested = suggested_quantity(
                ((original.attributes if original else None) or {}).get("quantity")
            )
            groups[label] = CountedGroup(
                scene_object_ids=[
                    item.id for item in confirmed if item.label.strip().casefold() == label
                ],
                label=obj.label,
                quantity=quantity,
                suggested_quantity=suggested,
                source=(
                    "entered"
                    if suggested is None
                    else "confirmed"
                    if suggested == quantity
                    else "corrected"
                ),
            ).model_dump(mode="json", by_alias=True)
        draft = dict(
            c.execute(
                select(sessions.c.analysis_draft).where(
                    sessions.c.id == session_id,
                )
            ).scalar_one()
            or {}
        )
        draft["countedGroups"] = list(groups.values())
        c.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                analysis_draft=draft,
            )
        )
        return draft["countedGroups"]

    def _save_review_markers(self, c, session_id, request, manual_ids):
        """The photo marker number each kept object had on the review screen."""
        draft = dict(
            c.execute(
                select(sessions.c.analysis_draft).where(
                    sessions.c.id == session_id,
                )
            ).scalar_one()
            or {}
        )
        draft["reviewMarkers"] = review_marker_numbers(
            draft.get("objects", []),
            request.accepted_object_ids,
            [manual_ids[item.id] for item in request.added_objects],
            draft.get("suggestedSceneObjectIds", []),
        )
        c.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                analysis_draft=draft,
            )
        )

    def _plan_missions(
        self, c, session, profile, objects, counted_groups, relations, mission_choices=None,
        language_context=_LANGUAGE_CONTEXT_UNSET,
    ):
        """Snapshot the lesson's mission plan from the confirmed facts before generation."""
        if language_context is _LANGUAGE_CONTEXT_UNSET:
            language_context = session_language_context(session, profile)
        candidates = lesson_missions(session.mode, profile, language_context)
        if not candidates:
            return None
        history_drafts = c.execute(
            select(sessions.c.analysis_draft).where(
                sessions.c.language_profile_id == profile["id"],
                sessions.c.id != session.id,
                sessions.c.mode == SessionMode.LESSON,
            )
        ).scalars().all()
        history = [
            item["missionId"]
            for saved in history_drafts
            for item in (saved or {}).get("missionPlan", [])
            if isinstance(item, dict) and isinstance(item.get("missionId"), str)
        ]
        plan = plan_missions(
            candidates, objects, relations, counted_groups, history, mission_choices,
            language_context,
        )
        draft = dict(c.execute(select(sessions.c.analysis_draft).where(
            sessions.c.id == session.id,
        )).scalar_one() or {})
        if language_context is not None:
            draft["languageContext"] = language_context.snapshot()
        previous_entries = {
            (
                item.get("missionId"),
                item.get("practiceLevel"),
                item.get("contentVersion"),
            ): item
            for item in draft.get("missionPlan", [])
            if isinstance(item, dict)
        }
        markers = draft.get("reviewMarkers") or {}
        mission_plan = []
        for mission in plan:
            entry = mission_snapshot(mission)
            previous = previous_entries.get((
                entry["missionId"], entry["practiceLevel"], entry["contentVersion"],
            ), {})
            entry.update({
                key: value for key, value in previous.items()
                if key not in entry and key not in {"roleplayFacts", "learnerFacts"}
            })
            # A0: the learner's own choice when one was sent, else an assigned scenario.
            ownership = (mission_choices or {}).get("ownership") or {}
            preference = (mission_choices or {}).get("preference") or {}
            if str(mission.practice_level) == "A0" and mission.mission_id == "M04" and ownership:
                entry["learnerFacts"] = {
                    "ownedObjectId": ownership.get("sceneObjectId"),
                    "pretend": bool(ownership.get("pretend", False)),
                }
            elif (
                str(mission.practice_level) == "A0" and mission.mission_id == "M05"
                and preference
            ):
                compared = preference.get("sceneObjectIds", [])
                entry["learnerFacts"] = {
                    "preference": {
                        "sceneObjectIds": compared,
                        "chosenObjectId": preference.get("chosenObjectId"),
                        "reaction": preference.get("reaction") or (
                            "like" if len(compared) == 2 else None
                        ),
                    }
                }
            elif (
                scenario := assign_a0_scenario(mission, session.id, objects, markers)
            ) is not None:
                entry["learnerFacts"] = scenario
            if (
                str(mission.practice_level) == "A1"
                and mission.mission_id in {"M04", "M05"}
            ):
                entry["roleplayFacts"] = assign_roleplay(
                    mission, session.id, objects, markers
                )
            mission_plan.append(entry)
        draft["missionPlan"] = mission_plan
        draft.pop("missionGuidance", None)
        draft.pop("sceneShortfall", None)
        c.execute(update(sessions).where(sessions.c.id == session.id).values(
            analysis_draft=draft,
        ))
        # No mission fits: report what is short instead of a lesson that cannot be checked.
        return None if plan else scene_shortfall(
            candidates, objects, relations, counted_groups, mission_choices, language_context,
        )

    def _planned_missions(self, session, profile, language_context=_LANGUAGE_CONTEXT_UNSET):
        if language_context is _LANGUAGE_CONTEXT_UNSET:
            language_context = session_language_context(session, profile)
        if not lesson_missions(session.mode, profile, language_context):
            return []
        # Missing plans are rebuilt at claim time; a saved empty plan stays empty.
        return snapshot_missions((session.analysis_draft or {}).get("missionPlan"))

    def _reuse(self, c, session, asset, objects, relations):
        """The cache scope and scene templates for this session's content.

        Results are shared, and precomputed templates offered, only for
        unchanged curated content.
        """
        if asset is not None and asset.source == "preloaded":
            contents = [
                content
                for content in c.execute(
                    select(preloaded_scenes.c.content).where(
                        preloaded_scenes.c.media_asset_id == asset.id,
                        preloaded_scenes.c.is_active.is_(True),
                    )
                ).scalars()
                if is_curated_content(session.id, content, objects, relations)
            ]
            if contents:
                return CacheScope.public(), TemplateSet.from_content(contents) or None
        return CacheScope.user(self.user_id), None

    def _current_generation(self, c, claim):
        """The session while ``claim`` still owns it; ``None`` marks a stale result."""
        session = self._session(c, claim.session_id, claim.profile_id)
        if session.status in TERMINAL:
            return None
        if self._generation_revision(c, claim.session_id) != claim.revision:
            logger.info(
                "Discarding stale task generation %s for session %s.",
                claim.revision,
                claim.session_id,
            )
            return None
        return session

    def _generate_tasks(self, claim):
        """Translate → checkpoint task 1 → lessons/clues → persist the full plan.

        Model calls run with no transaction or user lock open. Each write first
        checks that ``claim`` is still the session's current generation.
        """
        session_id, profile = claim.session_id, claim.profile
        session = claim.session
        lessons = []
        ispy_clues = []
        ispy_descriptions = None
        introduction_id = None
        objects, relations = list(claim.objects), claim.relations
        # Every lesson, with or without missions, translates with its language pack. With
        # no translator configured (tests, local runs without AI), a lesson without missions
        # keeps the deterministic default lesson from catalog words; missions need the pack.
        context = getattr(claim, "language_context", None)
        if context is None:
            raise LearningTaskGenerationError(
                f"No language pack is ready for {profile['target_language_code']!r} lessons."
            )
        if not self.translator and claim.missions:
            raise LearningTaskGenerationError("Pack lessons require accepted scene translations.")
        payload = translation_payload(
            profile["target_language_code"],
            claim.title,
            session.session_summary or "Confirmed scene vocabulary.",
            objects,
            relations,
        )
        translated_scene = None
        if self.translator:
            with _timed("translation", session_id):
                translated_scene = self.translator.translate(
                    payload, **claim.generation_options, language_context=context,
                )

        # Checkpoint: commit translations and task 1 before the slower lesson
        # and clue calls, so the learner can start while tasks are built.
        with self.transaction() as c:
            session = self._current_generation(c, claim)
            if session is None:
                return
            # Rebuild tasks from scratch for the accepted objects.
            c.execute(delete(session_tasks).where(session_tasks.c.session_id == session_id))
            draft = dict(session.analysis_draft or {})
            draft.pop("missionChecks", None)
            c.execute(
                update(sessions).where(sessions.c.id == session_id).values(analysis_draft=draft)
            )
            supplemental_vocabulary = {}
            if self.translator:
                supplemental_vocabulary = self._store_translation(
                    c, session, profile, objects, translated_scene
                )
            objects, relations = self._scene_objects(c, session)
            words, translations = self._words(c, session, objects)
            rebuilt = build_tasks(
                session_id,
                objects,
                words,
                translations,
                False,
                translated_scene if self.translator else _translation_preview(session),
                supplemental_vocabulary,
                relations,
                # Without a translation the default lesson uses catalog words, not the pack.
                language_context=context if self.translator else None,
            )
            introduction = next(task for task in rebuilt if task.kind == "vocabularyIntroduction")
            draft = dict(c.execute(select(sessions.c.analysis_draft).where(
                sessions.c.id == session_id,
            )).scalar_one() or {})
            draft["languageContext"] = context.snapshot()
            c.execute(update(sessions).where(sessions.c.id == session_id).values(
                analysis_draft=draft,
            ))
            introduction = personalize_introduction(introduction, claim.learner_history)
            rebuilt = [introduction if task.id == introduction.id else task for task in rebuilt]
            summary = personalization_summary(
                claim.learner_history,
                introduction,
                has_relations=bool(relations),
            )
            if claim.learner_history or (session.analysis_draft or {}).get("personalization"):
                draft = dict(
                    c.execute(
                        select(sessions.c.analysis_draft).where(
                            sessions.c.id == session.id,
                        )
                    ).scalar_one()
                    or {}
                )
                if summary:
                    draft["personalization"] = summary.model_dump(mode="json", by_alias=True)
                else:
                    draft.pop("personalization", None)
                c.execute(
                    update(sessions)
                    .where(sessions.c.id == session.id)
                    .values(
                        analysis_draft=draft,
                    )
                )
            introduction.order_index = 0
            c.execute(insert(session_tasks).values(**entity_values(introduction)))
            introduction_id = introduction.id
            if self.translator:
                # Translation is the moment a learner has collected these
                # words. Persist a "new" vocabulary record now, rather than
                # waiting for task completion, so leaving the lesson does not
                # discard their image vocabulary.
                for word in _unique_by_id([*words, *supplemental_vocabulary.values()]):
                    record_vocabulary_evidence(
                        c,
                        user_id=self.user_id,
                        vocabulary_item_id=word.id,
                        encounter=VocabularyEncounter(
                            id=uuid5(session_id, f"translated:{word.id}"),
                            user_id=self.user_id,
                            vocabulary_item_id=word.id,
                            session_id=session_id,
                            session_task_id=introduction.id,
                            encounter_type=VocabularyEncounterType.INTRODUCED,
                            outcome=VocabularyEncounterOutcome.COMPLETED,
                        ),
                    )

        mission_lessons, skipped_missions = [], []
        if claim.missions:
            # Mission lessons end at their summary. I-Spy is an optional,
            # separately created game that can reuse this scene afterwards.
            lesson = partial(
                self._mission_lessons,
                claim,
                objects,
                relations,
                words,
                translated_scene,
                skipped_missions,
            )
            mission_lessons = lesson()
        shortfall = None
        if not mission_lessons and lesson_missions(session.mode, profile, context):
            # Mission profiles never fall back to the unchecked regular lesson.
            shortfall = self._generation_shortfall(claim, session, objects, relations)
        if not mission_lessons and self.translator and shortfall is None:
            # Profiles without implemented missions keep the regular lesson.
            lessons, ispy_clues = self._lessons_and_clues(
                session_id,
                payload,
                translated_scene,
                objects,
                words,
                relations,
                claim.generation_options,
                history=lesson_history(claim.learner_history, introduction),
                history_scope=CacheScope.user(f"{self.user_id}:{claim.profile_id}"),
            )
        if (
            not mission_lessons
            and self.translator
            and self.ispy_guess_generator
            and shortfall is None
        ):
            ispy_descriptions = build_ispy_description_tasks(
                session_id,
                objects,
                words,
                _ispy_guess_context(payload, translated_scene, objects, relations),
            )

        with self.transaction() as c:
            session = self._current_generation(c, claim)
            if session is None:
                return
            if shortfall is not None:
                self._reopen_review(c, session, shortfall, skipped_missions)
                return
            learning = [task for task in rebuilt if task.kind not in {"ispyRound", "reflection"}]
            clues = ispy_clues or [task for task in rebuilt if task.kind == "ispyRound"]
            # An empty list means no target had confirmed description facts.
            descriptions = (
                ispy_descriptions
                if ispy_descriptions is not None
                else [task for task in rebuilt if task.kind == "reflection"]
            )
            if lessons:
                # Generated lessons replace deterministic grammar/syntax exercises.
                learning = [
                    task for task in learning if task.kind == "vocabularyIntroduction"
                ] + lessons
            rebuilt = [*learning, *clues, *descriptions]
            if skipped_missions:
                draft = dict(session.analysis_draft or {})
                draft["skippedMissions"] = skipped_missions
                c.execute(
                    update(sessions)
                    .where(sessions.c.id == session_id)
                    .values(
                        analysis_draft=draft,
                    )
                )
                session = session.model_copy(update={"analysis_draft": draft})
            if mission_lessons:
                rebuilt = [
                    *(task for task in rebuilt if task.id == introduction_id),
                    *mission_lessons,
                ]
                m06_task = next(
                    (
                        task
                        for task in mission_lessons
                        if task.public_content.mission_key
                        and task.public_content.mission_key[0] == "M06"
                    ),
                    None,
                )
                if m06_task is not None:
                    draft = dict(session.analysis_draft or {})
                    plan = list(draft.get("missionPlan") or [])
                    for entry in plan:
                        if entry.get("missionId") == "M06":
                            entry["transaction"] = m06_task.answer_key.mission_state["transaction"]
                    draft["missionPlan"] = plan
                    c.execute(
                        update(sessions)
                        .where(sessions.c.id == session_id)
                        .values(
                            analysis_draft=draft,
                        )
                    )
                    session = session.model_copy(update={"analysis_draft": draft})
            if summary and summary.practice_focuses:
                available = {task.public_content.focus for task in lessons}
                summary.practice_focuses = [
                    focus for focus in summary.practice_focuses if focus in available
                ]
                draft = dict(session.analysis_draft or {})
                if summary.returning_words or summary.practice_focuses:
                    draft["personalization"] = summary.model_dump(mode="json", by_alias=True)
                else:
                    draft.pop("personalization", None)
                c.execute(
                    update(sessions)
                    .where(sessions.c.id == session_id)
                    .values(
                        analysis_draft=draft,
                    )
                )
            for index, task in enumerate(rebuilt):
                if task.id == introduction_id:
                    # Preserve any progress/attempts already made in task 1.
                    continue
                task.order_index = index
                c.execute(
                    upsert(session_tasks)
                    .values(**entity_values(task))
                    .on_conflict_do_nothing(index_elements=["id"])
                )
            self._transition(c, session, "inProgress")

    @staticmethod
    def _generation_shortfall(claim, session, objects, relations):
        """What the confirmed scene lacks when no planned mission produced a lesson."""
        draft = session.analysis_draft or {}
        context = getattr(claim, "language_context", None)
        shortfall = scene_shortfall(
            lesson_missions(session.mode, claim.profile, context),
            objects,
            relations,
            claim.counted_groups,
            draft.get("missionChoices") or {},
            context,
        )
        if shortfall is not None:
            return shortfall
        # The missions fitted the photo but none had reviewed content to check.
        return SceneShortfall(
            missing=SHORTFALL_KINDS,
            missions=tuple(
                {
                    "missionId": mission.mission_id,
                    "title": mission.title,
                    "missing": [],
                    "reasons": [
                        "Linguini couldn't build checked questions from these facts."
                    ],
                }
                for mission in claim.missions
            ),
        )

    def _reopen_review(self, c, session, shortfall, skipped):
        """Drop the partial lesson and send the learner back to review with what is short."""
        c.execute(delete(session_tasks).where(session_tasks.c.session_id == session.id))
        draft = {**(session.analysis_draft or {}), "sceneShortfall": shortfall.as_json()}
        if skipped:
            draft["skippedMissions"] = skipped
        logger.info(
            "Session %s has no checkable mission; reopening review (missing=%s).",
            session.id,
            ",".join(shortfall.missing),
        )
        self._transition(c, session, "awaitingObjectReview", analysis_draft=draft)

    def _mission_lessons(self, claim, objects, relations, words, translated_scene, skipped):
        """One validated lesson per planned mission, generated from the language pack.

        Mission lessons come only from packs: a planned mission the session's pack does not
        own fails generation into the normal recoverable error state. A role-play mission
        whose saved facts are no longer valid is skipped and recorded in ``skipped``.
        """
        language = claim.profile["target_language_code"]
        context = getattr(claim, "language_context", None)
        lessons = []
        for planned in claim.missions:
            mission = lesson_mission(planned)
            if context is None or not context.owns(mission.mission_id):
                raise LearningTaskGenerationError(
                    f"{mission.mission_id} has no language pack lesson for {language!r}."
                )
            roleplay = (claim.roleplay_facts or {}).get(mission.mission_id)
            if str(mission.practice_level) == "A1" and mission.mission_id in {"M04", "M05"} and (
                len(parse_roleplay_facts(roleplay, [obj.id for obj in objects]) or []) != 3
            ):
                skipped.append(dict(missionId=mission.mission_id, reason="invalidRoleplay"))
                continue
            if self.learning_task_generator is None:
                raise LearningTaskGenerationError(
                    f"{mission.mission_id} pack generation needs a configured provider."
                )
            # Missions reach this point through the existing eligibility/review flow.
            # A pack failure propagates to the normal recoverable generation error state.
            built = self.learning_task_generator.generate_pack_lesson(
                mission, language, objects, relations, words, translated_scene,
                session_id=claim.session_id, review_markers=claim.review_markers or {},
                cache_scope=claim.cache_scope,
                register=context.display.register_id,
                language_context=context,
                counted_groups=claim.counted_groups or (),
                mission_context={
                    "roleplay_facts": roleplay,
                    "learner_facts": (claim.learner_facts or {}).get(mission.mission_id),
                    # M06's saved order and reply history, as dev's builder reads them.
                    "progress": claim.mission_progress or {},
                },
            )
            lessons.extend(built if isinstance(built, list) else [built])
        return lessons

    def _store_translation(self, c, session, profile, objects, translated_scene):
        """Persist every translated scene term and link objects to their words."""
        draft = {
            **(session.analysis_draft or {}),
            "translationPreview": translated_scene.model_dump(mode="json", by_alias=True),
        }
        c.execute(update(sessions).where(sessions.c.id == session.id).values(analysis_draft=draft))
        translated_objects = {row.key: row for row in translated_scene.objects}
        for obj in objects:
            translated = translated_objects[str(obj.id)]
            word, _source_translation = bootstrap_word(
                c,
                profile["target_language_code"],
                profile["source_language_code"],
                translated.translation,
                obj.label,
                gender=translated.gender,
                phonetic_text=translated.phonetic_text,
            )
            c.execute(
                update(scene_objects)
                .where(scene_objects.c.id == obj.id)
                .values(vocabulary_item_id=word.id)
            )
        supplemental = {}
        for term_type, part_of_speech, terms in (
            ("attribute", "adjective", translated_scene.attributes),
            ("relationship", "preposition", translated_scene.relationships),
        ):
            for term in terms:
                word, _ = bootstrap_word(
                    c,
                    profile["target_language_code"],
                    profile["source_language_code"],
                    term.translation,
                    term.source,
                    part=part_of_speech,
                    phonetic_text=term.phonetic_text,
                )
                supplemental[(term_type, str(term.key))] = word
        return supplemental

    def _words(self, c, session, objects):
        """Each object's vocabulary item and translation, in object order."""
        vocabulary, vocabulary_translations = self._vocabulary(c, session, objects)
        words_by_id = {word.id: word for word in vocabulary}
        translations_by_id = {word.vocabulary_item_id: word for word in vocabulary_translations}
        if any(
            obj.vocabulary_item_id not in words_by_id
            or obj.vocabulary_item_id not in translations_by_id
            for obj in objects
        ):
            raise PracticeConflictError("Every selected object needs a word and translation.")
        return (
            [words_by_id[obj.vocabulary_item_id] for obj in objects],
            [translations_by_id[obj.vocabulary_item_id] for obj in objects],
        )

    def _lessons(
        self,
        session_id,
        payload,
        translated_scene,
        relations,
        options=None,
        *,
        history=None,
        history_scope=None,
    ):
        if not self.learning_task_generator:
            return []
        try:
            lesson_payload = learning_task_payload(payload, translated_scene, relations)
            lesson_options = options or {}
            if history:
                lesson_payload["learnerHistory"] = history
                lesson_options = {"cache_scope": history_scope, "templates": None}
            with _timed("learning-task generation", session_id):
                return build_grammar_lessons(
                    session_id,
                    self.learning_task_generator.generate(
                        lesson_payload,
                        **lesson_options,
                    ),
                )
        except Exception:
            logger.exception(
                "Learning-task generation failed for session %s; "
                "using the deterministic lesson plan.",
                session_id,
            )
            return []

    def _clues(
        self,
        session_id,
        payload,
        translated_scene,
        objects,
        words,
        relations,
        options=None,
    ):
        if not self.ispy_clue_generator:
            return []
        try:
            with _timed("I-Spy clue generation", session_id):
                return build_ispy_clue_tasks(
                    session_id,
                    self.ispy_clue_generator.generate(
                        ispy_clue_payload(payload, translated_scene, objects, relations),
                        **(options or {}),
                    ),
                    objects,
                    words,
                )
        except ISpyClueGenerationError:
            logger.exception("I-Spy clue generation failed for session %s.", session_id)
            return []

    def _lessons_and_clues(
        self,
        session_id,
        payload,
        translated_scene,
        objects,
        words,
        relations,
        options=None,
        *,
        history=None,
        history_scope=None,
    ):
        """Run the two independent generation calls at once, each with its own fallback.

        The clue call runs on a one-thread executor owned by this job rather than
        the shared background pool, so each job adds at most one thread and a
        saturated pool cannot deadlock waiting on itself.
        """
        lesson_options = {"options": options}
        if history:
            lesson_options.update(history=history, history_scope=history_scope)
        lessons = partial(
            self._lessons,
            session_id,
            payload,
            translated_scene,
            relations,
            **lesson_options,
        )
        clues = partial(
            self._clues,
            session_id,
            payload,
            translated_scene,
            objects,
            words,
            relations,
            options=options,
        )
        return self._alongside_clues(lessons, clues)

    def _alongside_clues(self, lessons, clues):
        if not (self.learning_task_generator and self.ispy_clue_generator):
            return lessons(), clues()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ispy-clues") as pool:
            pending = pool.submit(clues)
            return lessons(), pending.result()

    def finish(self, session_id, profile_id, abandon=False):
        with self.transaction() as c:
            session = self._session(c, session_id, profile_id)
            target = "abandoned" if abandon else "completed"
            if session.status == target:
                return session
            if session.status in TERMINAL:
                raise PracticeConflictError("Session is already terminal.")
            tasks = self._tasks(c, session.id)
            mission_session = any(
                getattr(task.public_content, "mission_id", None) for task in tasks
            )
            required_tasks = (
                [task for task in tasks if task.kind not in {"ispyRound", "reflection"}]
                if mission_session
                else tasks
            )
            if not abandon and (
                session.status == "generatingTasks"
                or not required_tasks
                or any(t.status not in {"completed", "skipped"} for t in required_tasks)
            ):
                raise PracticeConflictError("Complete or skip every task first.")
            session = self._transition(c, session, target)
            if not abandon and session.mode == SessionMode.LESSON:
                award(
                    c,
                    user_id=self.user_id,
                    event_type="sessionCompleted",
                    idempotency_key=f"session:{session.id}",
                    language_profile_id=session.language_profile_id,
                    session_id=session.id,
                )
                record_completion(c, self.user_id, session.id)
                ispy = self._ispy_summary(c, session.id)
                if (
                    all(task.status == "completed" for task in tasks)
                    and ispy["ispy_attempt_count"] > 0
                    and ispy["ispy_correct_count"] == ispy["ispy_attempt_count"]
                ):
                    award(
                        c,
                        user_id=self.user_id,
                        event_type="perfectSession",
                        idempotency_key=f"perfect:{session.id}",
                        language_profile_id=session.language_profile_id,
                        session_id=session.id,
                    )
            return session

    def summary(self, session_id, profile_id):
        with self.read_connection() as c:
            session = self._session(c, session_id, profile_id)
            learned = (
                c.execute(
                    select(vocabulary_encounters.c.vocabulary_item_id)
                    .where(
                        vocabulary_encounters.c.session_id == session.id,
                        vocabulary_encounters.c.user_id == self.user_id,
                    )
                    .distinct()
                )
                .scalars()
                .all()
            )
            return SessionSummaryResponse(
                session=session,
                progress=task_progress(self._tasks(c, session.id)),
                learned_vocabulary_ids=learned,
                basil_earned=session_basil(c, self.user_id, session.id),
                xp_earned=c.execute(
                    select(func.coalesce(func.sum(xp_events.c.amount), 0))
                    .select_from(xp_events)
                    .where(
                        xp_events.c.session_id == session.id,
                        xp_events.c.user_id == self.user_id,
                    )
                ).scalar_one(),
                completed_lessons_count=c.execute(
                    select(func.count())
                    .select_from(sessions)
                    .where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.status == "completed",
                    )
                ).scalar_one(),
                **self._ispy_summary(c, session.id),
            )

    def _ispy_summary(self, c, session_id):
        """Count graded clue attempts, plus one round per described task.

        A described task succeeds only once its clear match is confirmed, so
        unresolved, ambiguous and failed evaluations never count as correct.
        """
        rows = c.execute(
            select(
                session_tasks.c.id,
                session_tasks.c.status,
                task_attempts.c.is_correct,
                task_attempts.c.evaluation_details["version"].astext.label("version"),
            )
            .join(session_tasks, session_tasks.c.id == task_attempts.c.session_task_id)
            .where(session_tasks.c.session_id == session_id, session_tasks.c.phase == "ispy")
        ).all()
        graded = [
            row.is_correct for row in rows if row.version != ISPY_DESCRIPTION_EVALUATION_VERSION
        ]
        rounds = {
            row.id: row.status == "completed"
            for row in rows
            if row.version == ISPY_DESCRIPTION_EVALUATION_VERSION
        }
        return {
            "ispy_correct_count": sum(outcome is True for outcome in graded) + sum(rounds.values()),
            "ispy_attempt_count": sum(outcome is not None for outcome in graded) + len(rounds),
        }

    def _encounter(
        self,
        c,
        task,
        event_id,
        outcome,
        introduced=False,
        vocabulary_item_id=None,
        session=None,
    ):
        explicit_vocabulary_item_id = vocabulary_item_id
        resolved_vocabulary_item_id = vocabulary_item_id or task.vocabulary_item_id
        # Standalone I-Spy games never advance vocabulary proficiency.
        if not resolved_vocabulary_item_id or (session and session.mode == SessionMode.ISPY):
            return
        # A grouped vocabulary-introduction attempt writes one encounter per
        # taught word. Give explicitly supplied words distinct event IDs even
        # when the task itself also has a primary vocabulary-item ID.
        event_scope = (
            "vocabulary"
            if explicit_vocabulary_item_id is None and task.vocabulary_item_id
            else f"vocabulary:{resolved_vocabulary_item_id}"
        )
        event = VocabularyEncounter(
            id=uuid5(event_id, event_scope),
            user_id=self.user_id,
            vocabulary_item_id=resolved_vocabulary_item_id,
            session_id=task.session_id,
            session_task_id=task.id,
            encounter_type="introduced" if introduced else "practised",
            outcome=outcome,
        )
        record_vocabulary_evidence(
            c,
            user_id=self.user_id,
            vocabulary_item_id=resolved_vocabulary_item_id,
            encounter=event,
        )

    def _task_row(self, c, task_id):
        row = (
            c.execute(
                select(session_tasks)
                .join(sessions, sessions.c.id == session_tasks.c.session_id)
                .join(language_profiles, language_profiles.c.id == sessions.c.language_profile_id)
                .where(
                    session_tasks.c.id == task_id,
                    sessions.c.user_id == self.user_id,
                    language_profiles.c.is_active.is_(True),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PracticeNotFoundError("Task not found.")
        return SessionTask.model_validate(dict(row))

    def _evaluates_description(self, task):
        return bool(_describes_object(task) and self.ispy_guess_generator)

    def _evaluation_lease(self):
        seconds = getattr(
            self.ispy_guess_generator, "max_duration_seconds", DEFAULT_EVALUATION_SECONDS
        )
        return timedelta(seconds=seconds + EVALUATION_LEASE_MARGIN_SECONDS)

    def _claim_description(self, task_id, request):
        """Lease a model-graded I-Spy attempt; ``None`` when no model call is due.

        A live lease for the same key yields ``PendingEvaluation`` (or a conflict
        if the input differs). A missing, expired or other-key lease is taken
        over. Saved attempts, inactive tasks and invalid input fall through to
        ``_apply_task_action``, which returns or rejects them.
        """
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            if request.input_mode == "text":
                check_clue(task.public_content, request)
            if not self._evaluates_description(task) or request.input_mode != "text":
                return None
            attempt_id = _attempt_id(task, request)
            session = self._session(c, task.session_id)
            if (
                c.execute(
                    select(task_attempts.c.id).where(task_attempts.c.id == attempt_id)
                ).first()
                or session.status != "inProgress"
                or task.status in {"completed", "skipped"}
            ):
                return None
            fingerprint = _request_fingerprint(request)
            held = c.execute(
                select(
                    task_evaluation_claims.c.evaluation_claim_id,
                    task_evaluation_claims.c.evaluation_claim_fingerprint,
                    (task_evaluation_claims.c.evaluation_claim_expires_at > func.now()).label(
                        "live"
                    ),
                ).where(task_evaluation_claims.c.id == task.id)
            ).one()
            if held.live and held.evaluation_claim_id == attempt_id:
                if held.evaluation_claim_fingerprint != fingerprint:
                    raise PracticeConflictError("Attempt key already used for another answer.")
                return PendingEvaluation(task.id, attempt_id)
            c.execute(
                update(task_evaluation_claims)
                .where(task_evaluation_claims.c.id == task.id)
                .values(
                    evaluation_claim_id=attempt_id,
                    evaluation_claim_fingerprint=fingerprint,
                    evaluation_claim_expires_at=func.now() + self._evaluation_lease(),
                )
            )
            return DescriptionClaim(
                task.id,
                attempt_id,
                task.answer_key.scene_description_context,
                request.text,
                str(task.session_id),
            )

    def _evaluate_description(self, claim):
        try:
            return self.ispy_guess_generator.guess(
                claim.context, claim.learner_text, session_id=claim.session_id
            )
        except ISpyGuessError:
            logger.exception("I-Spy description guess failed for task %s.", claim.task_id)
            return None

    def _await_evaluation(self, pending):
        """Waits while the lease holder evaluates; ``False`` if another key took over."""
        delay, max_delay = EVALUATION_POLL_SECONDS
        while True:
            time.sleep(delay)
            with self.engine.connect() as c:
                row = c.execute(
                    select(
                        task_evaluation_claims.c.evaluation_claim_id,
                        (task_evaluation_claims.c.evaluation_claim_expires_at > func.now()).label(
                            "live"
                        ),
                        select(task_attempts.c.id)
                        .where(task_attempts.c.id == pending.attempt_id)
                        .exists()
                        .label("saved"),
                    ).where(task_evaluation_claims.c.id == pending.task_id)
                ).one()
            if row.saved or row.evaluation_claim_id is None or not row.live:
                return True
            if row.evaluation_claim_id != pending.attempt_id:
                return False
            delay = min(delay * 2, max_delay)

    def _release_claim(self, claim):
        try:
            with self.engine.begin() as c:
                c.execute(
                    update(task_evaluation_claims)
                    .where(
                        task_evaluation_claims.c.id == claim.task_id,
                        task_evaluation_claims.c.evaluation_claim_id == claim.attempt_id,
                    )
                    .values(**NO_EVALUATION_CLAIM)
                )
        except SQLAlchemyError:
            logger.exception("Could not release the evaluation claim for task %s.", claim.task_id)

    def task_action(self, task_id, action, request=None):
        """Lease → one model call with no transaction open → persist if still leased."""
        if action != "attempt":
            return self._apply_task_action(task_id, action, request, None)
        while True:
            claim = self._claim_description(task_id, request)
            if not isinstance(claim, PendingEvaluation):
                break
            if not self._await_evaluation(claim):
                raise PracticeConflictError(
                    "This task changed while your description was evaluated. Retry the action."
                )
        if claim is None:
            return self._apply_task_action(task_id, action, request, None)
        try:
            evaluation = DescriptionEvaluation(claim.attempt_id, self._evaluate_description(claim))
            return self._apply_task_action(task_id, action, request, evaluation)
        except Exception:
            self._release_claim(claim)
            raise

    def _apply_task_action(self, task_id, action, request, evaluation):
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            session = self._session(c, task.session_id)
            attempt = None
            if action == "attempt":
                payload = _response_payload(request)
                attempt_id = _attempt_id(task, request)
                saved = (
                    c.execute(select(task_attempts).where(task_attempts.c.id == attempt_id))
                    .mappings()
                    .one_or_none()
                )
                if saved:
                    attempt = TaskAttempt.model_validate(dict(saved))
                    if attempt.response_payload != payload:
                        raise PracticeConflictError("Attempt key already used for another answer.")
                elif request.input_mode == "text":
                    check_clue(task.public_content, request)
            retry = (
                attempt is not None
                or (action == "complete" and task.status == "completed")
                or (action == "skip" and task.status == "skipped")
            )
            if not retry:
                early_vocabulary = (
                    session.status == "generatingTasks" and task.kind == "vocabularyIntroduction"
                )
                if (session.status != "inProgress" and not early_vocabulary) or task.status in {
                    "completed",
                    "skipped",
                }:
                    raise PracticeConflictError(
                        f"Task or session is not active; session is '{session.status}'."
                    )
                values = {}
                if action == "start":
                    values = dict(status="inProgress", started_at=task.started_at or utc_now())
                elif action == "skip":
                    values = dict(
                        status="skipped", skipped_at=utc_now(), skip_reason=request.reason
                    )
                elif action == "complete":
                    if task.kind not in READ_TASKS or (
                        task.kind == "vocabularyIntroduction" and task.public_content.words
                    ):
                        raise PracticeConflictError("Submit an answer or skip this task.")
                    values = dict(
                        status="completed",
                        completed_at=utc_now(),
                        started_at=task.started_at or utc_now(),
                    )
                    if task.kind == "vocabularyIntroduction":
                        self._encounter(
                            c, task, task.id, "completed", introduced=True, session=session
                        )
                elif action == "attempt":
                    evaluation_details = None
                    question_results = {}
                    if self._evaluates_description(task):
                        if request.input_mode != "text":
                            raise PracticeConflictError(
                                "I-Spy descriptions must be submitted as text."
                            )
                        if (
                            evaluation is None
                            or evaluation.attempt_id != attempt_id
                            or c.execute(
                                select(task_evaluation_claims.c.evaluation_claim_id).where(
                                    task_evaluation_claims.c.id == task.id
                                )
                            ).scalar_one()
                            != attempt_id
                        ):
                            raise PracticeConflictError(
                                "This task changed while your description was evaluated. "
                                "Retry the action."
                            )
                        interpretation = interpret_guess(evaluation.guess, task.scene_object_id)
                        correct = OUTCOME_CORRECTNESS[interpretation.outcome]
                        feedback_message = (
                            EVALUATION_FAILED_MESSAGE
                            if evaluation.guess is None
                            else evaluation.guess.feedback
                        )
                        evaluation_details = interpretation.model_dump(mode="json", by_alias=True)
                    else:
                        if task.kind == "grammarLesson" and task.public_content.check_each_question:
                            stored_checks = (
                                (session.analysis_draft or {})
                                .get("missionChecks", {})
                                .get(str(task.id), {})
                            )
                            question_ids = {
                                question.question_id for question in task.public_content.questions
                            }
                            if set(stored_checks) != question_ids:
                                raise PracticeConflictError(
                                    "Check every lesson question before submitting."
                                )
                            if any(
                                request.answers.get(question_id)
                                != stored_checks[question_id]["answer"]
                                for question_id in question_ids
                            ):
                                raise PracticeConflictError(
                                    "Submitted answers must match the answers checked in "
                                    "this lesson."
                                )
                        correct = evaluate(task, request)
                        feedback_message = (
                            "Reflection recorded."
                            if correct is None
                            else (
                                "Correct."
                                if correct
                                else "Not quite. Review this word and try it in another session."
                            )
                        )
                    if request.input_mode == "vocabularyReview":
                        question_results = {
                            question.question_id: _lesson_answer_is_correct(
                                task,
                                question.question_id,
                                request.answers.get(question.question_id, ""),
                            )
                            for question in task.public_content.questions
                        }
                        correct_count = sum(question_results.values())
                        # Released only with the graded attempt so each question
                        # can show its own correct answer.
                        correct_answers = {
                            question.question_id: expected
                            for question in task.public_content.questions
                            if (
                                expected := task.answer_key.correct_option_ids.get(
                                    question.question_id
                                )
                            )
                        }
                        server_assistance = None
                        if task.public_content.mission_id == "M06":
                            server_assistance = {
                                question_id: m06_check_supports(saved)
                                for question_id, saved in (
                                    (session.analysis_draft or {})
                                    .get("missionChecks", {})
                                    .get(str(task.id), {})
                                    .items()
                                )
                            }
                        evaluation_details = (
                            review_details(
                                task,
                                request,
                                question_results,
                                correct_answers,
                                assistance_by_question=server_assistance,
                            )
                            if task.answer_key.question_evaluations
                            else {
                                "questionResults": question_results,
                                "correctAnswers": correct_answers,
                            }
                        )
                        feedback_message = (
                            f"{correct_count} of {len(question_results)} questions correct."
                        )
                    attempt = TaskAttempt(
                        id=attempt_id,
                        session_task_id=task.id,
                        attempt_number=_next_attempt_number(c, task.id),
                        input_mode=request.input_mode,
                        response_payload=payload,
                        is_correct=correct,
                        score=None if correct is None else int(correct),
                        feedback={"message": feedback_message},
                        evaluation_details=evaluation_details,
                    )
                    if request.input_mode == "vocabularyReview":
                        outcomes = {
                            item["questionId"]: item
                            for item in (evaluation_details or {}).get("questionOutcomes", [])
                        }
                        for question in task.public_content.questions:
                            prior = question_event(c, self.user_id, task.id, question.question_id)
                            if (
                                prior
                                and not getattr(question, "allow_retry", False)
                                and prior["answer"] != request.answers[question.question_id]
                            ):
                                raise PracticeConflictError(
                                    "Submitted answers must match the first accepted answers."
                                )
                            record_question(
                                c,
                                self.user_id,
                                session,
                                task,
                                question.question_id,
                                request.answers[question.question_id],
                                question_results[question.question_id],
                                outcomes.get(question.question_id, {"evidenceType": "recognition"}),
                            )
                    c.execute(insert(task_attempts).values(**entity_values(attempt)))
                    if (
                        session.mode == SessionMode.LESSON
                        and request.input_mode != "vocabularyReview"
                        and (evaluation is None or evaluation.guess is not None)
                    ):
                        reward_basil(
                            c,
                            self.user_id,
                            f"task:{task.id}",
                            payload={
                                "sessionId": str(session.id),
                                "policyVersion": "legacy-practice.v1",
                            },
                        )
                    if evaluation is not None:
                        c.execute(
                            update(task_evaluation_claims)
                            .where(task_evaluation_claims.c.id == task.id)
                            .values(**NO_EVALUATION_CLAIM)
                        )
                    if (
                        correct is True
                        and task.phase == "ispy"
                        and evaluation is None
                        and session.mode == SessionMode.LESSON
                    ):
                        award(
                            c,
                            user_id=self.user_id,
                            event_type="ispyCorrect",
                            idempotency_key=f"attempt:{attempt.id}",
                            language_profile_id=session.language_profile_id,
                            session_id=task.session_id,
                        )
                    if evaluation is None:
                        self._encounter(
                            c,
                            task,
                            attempt.id,
                            "completed"
                            if correct is None
                            else ("correct" if correct else "incorrect"),
                            session=session,
                        )
                    if task.kind == "vocabularyIntroduction" and task.public_content.words:
                        mission_task = task.public_content.mission_key is not None or bool(
                            (session.analysis_draft or {}).get("missionPlan")
                        )
                        for learning_word in task.public_content.words:
                            word_correct = (
                                question_results.get(f"word-{learning_word.learning_key}", correct)
                                if mission_task
                                else correct
                            )
                            self._encounter(
                                c,
                                task,
                                attempt.id,
                                "correct" if word_correct else "incorrect",
                                introduced=True,
                                vocabulary_item_id=learning_word.vocabulary_item_id,
                                session=session,
                            )
                    if task.kind == "grammarLesson" and task.public_content.mission_key is not None:
                        for vocabulary_item_id, word_correct in word_results(
                            task, question_results
                        ).items():
                            self._encounter(
                                c,
                                task,
                                attempt.id,
                                "correct" if word_correct else "incorrect",
                                vocabulary_item_id=vocabulary_item_id,
                                session=session,
                            )
                    if evaluation is None:
                        values = dict(
                            status="completed",
                            completed_at=utc_now(),
                            started_at=task.started_at or utc_now(),
                        )
                    else:
                        # Described tasks finish only via ``confirm_guess``.
                        values = dict(status="inProgress", started_at=task.started_at or utc_now())
                else:
                    raise PracticeConflictError("Unknown task action.")
                c.execute(
                    update(session_tasks).where(session_tasks.c.id == task.id).values(**values)
                )
                if values["status"] == "completed":
                    self._award_completion(c, task, session)
            session_missions(c, self.user_id, session.id, persist=True)
            return self._action_response(c, task, attempt)

    def confirm_guess(self, task_id, attempt_id):
        """Complete a described task when the learner accepts its latest clear match.

        Confirming an older attempt, a non-clear outcome, or while a newer clue
        is being evaluated is rejected; repeating a confirmation is a no-op.
        """
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            if not _describes_object(task):
                raise PracticeConflictError("Only I-Spy descriptions can confirm a guess.")
            latest = (
                c.execute(
                    select(task_attempts)
                    .where(task_attempts.c.session_task_id == task.id)
                    .order_by(task_attempts.c.attempt_number.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if latest is None or latest["id"] != attempt_id:
                raise PracticeConflictError("Only the latest guess can be confirmed.")
            attempt = TaskAttempt.model_validate(dict(latest))
            try:
                outcome = ISpyDescriptionEvaluation.model_validate(
                    attempt.evaluation_details or {}
                ).outcome
            except ValueError:
                outcome = None
            if outcome != "clearMatch":
                raise PracticeConflictError("Only a clear match can be confirmed.")
            if task.status != "completed":
                session = self._session(c, task.session_id)
                if session.status != "inProgress" or task.status == "skipped":
                    raise PracticeConflictError(
                        f"Task or session is not active; session is '{session.status}'."
                    )
                if c.execute(
                    select(task_evaluation_claims.c.evaluation_claim_id).where(
                        task_evaluation_claims.c.id == task.id,
                        task_evaluation_claims.c.evaluation_claim_expires_at > func.now(),
                    )
                ).scalar_one_or_none():
                    raise PracticeConflictError("A newer clue is still being checked.")
                now = utc_now()
                c.execute(
                    update(session_tasks)
                    .where(session_tasks.c.id == task.id)
                    .values(status="completed", completed_at=now, started_at=task.started_at or now)
                )
                if session.mode == SessionMode.LESSON:
                    award(
                        c,
                        user_id=self.user_id,
                        event_type="ispyCorrect",
                        idempotency_key=f"ispy-correct:{task.id}",
                        language_profile_id=session.language_profile_id,
                        session_id=task.session_id,
                    )
                self._encounter(c, task, task.id, "completed", session=session)
                self._award_completion(c, task, session)
            return self._action_response(c, task, attempt)

    def _award_completion(self, c, task, session):
        if session.mode != SessionMode.LESSON:
            return
        award(
            c,
            user_id=self.user_id,
            event_type="taskCompleted",
            idempotency_key=f"task:{task.id}",
            language_profile_id=session.language_profile_id,
            session_id=task.session_id,
        )

    def _action_response(self, c, task, attempt):
        tasks = self._tasks(c, task.session_id)
        session = self._session(c, task.session_id)
        attempt_ids = c.execute(
            select(task_attempts.c.id).where(task_attempts.c.session_task_id == task.id)
        ).scalars()
        idempotency_keys = [
            f"task:{task.id}",
            f"ispy-correct:{task.id}",
            *(f"attempt:{attempt_id}" for attempt_id in attempt_ids),
        ]
        xp_earned = c.execute(
            select(func.coalesce(func.sum(xp_events.c.amount), 0)).where(
                xp_events.c.user_id == self.user_id,
                xp_events.c.session_id == task.session_id,
                xp_events.c.idempotency_key.in_(idempotency_keys),
            )
        ).scalar_one()
        return TaskActionResponse(
            task=SessionTaskPublic.from_internal(
                next(t for t in tasks if t.id == task.id), mode=session.mode
            ),
            attempt=attempt,
            next_task_id=next(
                (t.id for t in tasks if t.status not in {"completed", "skipped"}), None
            ),
            session_progress=task_progress(tasks),
            basil_earned=task_basil(c, self.user_id, task.id),
            xp_earned=xp_earned,
        )


def _describes_object(task):
    return bool(
        task.kind == "reflection"
        and task.phase == "ispy"
        and task.answer_key
        and task.answer_key.scene_description_context
    )


def _next_attempt_number(c, task_id):
    return c.execute(
        select(func.coalesce(func.max(task_attempts.c.attempt_number), 0) + 1).where(
            task_attempts.c.session_task_id == task_id
        )
    ).scalar_one()


def _attempt_id(task, request):
    return uuid5(task.id, "attempt:" + (request.idempotency_key or "single-evaluation"))


def _response_payload(request):
    exclude = {"idempotency_key"}
    # Optional support records are left out when absent so older payloads keep their shape.
    for name in ("assistance", "question_assistance"):
        if getattr(request, name, False) is None:
            exclude.add(name)
    return request.model_dump(mode="json", by_alias=False, exclude=exclude)


def _request_fingerprint(request):
    canonical = json.dumps(_response_payload(request), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate(task, request):
    """Small deterministic evaluator; never accepts client scores or answer keys."""
    mode = request.input_mode
    if task.kind in READ_TASKS and not (
        task.kind == "vocabularyIntroduction" and mode == "vocabularyReview"
    ):
        raise PracticeConflictError("This task is completed by reading it.")
    allowed = {
        "vocabularyIntroduction": {"vocabularyReview"},
        "grammarLesson": {"vocabularyReview"},
        "grammarPractice": {"text", "multipleChoice"},
        "sentenceBuilding": {"text"},
        "ispyRound": {"objectSelection", "multipleChoice"},
        "reflection": {"text"},
    }
    if mode not in allowed.get(task.kind, set()):
        raise PracticeConflictError(
            "Input mode is not supported for this task. Use typing or the offered choices."
        )
    if task.kind == "reflection":
        return None
    key = task.answer_key
    if key is None:
        raise PracticeConflictError("Task has no evaluation key.")
    if mode == "vocabularyReview":
        questions_by_id = {
            question.question_id: question for question in task.public_content.questions
        }
        if set(request.answers) != set(questions_by_id):
            raise PracticeConflictError("Answer every question in this lesson once.")
        if any(
            getattr(question, "interaction_type", "multipleChoice") == "multipleChoice"
            and answer not in {option.option_id for option in question.options}
            and not getattr(question, "typed_allowed", False)
            for question_id, answer in request.answers.items()
            for question in [questions_by_id[question_id]]
        ):
            raise PracticeConflictError("Select only choices offered by this lesson.")
        if not set(request.typed_answers).issubset(key.accepted_text_answers_by_vocabulary_id):
            raise PracticeConflictError("Typing practice contains an unknown word.")
        if any(
            item.question_id not in questions_by_id for item in request.question_assistance or []
        ):
            raise PracticeConflictError("Assistance names a question this lesson does not have.")
        if task.public_content.mission_key is not None and any(
            not set(item.supports) <= offered_supports(questions_by_id[item.question_id])
            for item in request.question_assistance or []
        ):
            raise PracticeConflictError("Assistance names support this question does not offer.")
        return all(
            _lesson_answer_is_correct(task, question_id, answer)
            for question_id, answer in request.answers.items()
        )
    if mode == "objectSelection":
        if request.scene_object_id not in {o.scene_object_id for o in task.public_content.options}:
            raise PracticeConflictError("Select an object offered by this task.")
        return request.scene_object_id == key.correct_scene_object_id
    if mode == "multipleChoice":
        options = task.public_content.options
        offered = {o.option_id for o in options} if task.kind == "ispyRound" else set(options)
        if request.option_id not in offered:
            raise PracticeConflictError("Select one of the offered choices.")
        return request.option_id == key.correct_option_id

    return normalize_answer(request.text) in {
        normalize_answer(answer) for answer in key.accepted_text_answers
    }
