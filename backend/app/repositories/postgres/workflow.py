"""Atomic normalized session workflow. Locks serialize each user's transitions."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from uuid import UUID, uuid5

from sqlalchemy import DateTime, and_, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

from app.ai.features.ispy_clues import ISpyClueGenerationError
from app.ai.features.ispy_guess import ISpyGuessError, ISpyGuessResult
from app.ai.features.learning_tasks import required_task_focuses
from app.ai.features.scene_analysis import RoutedSceneAnalyzer
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
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
    vocabulary_encounters,
    vocabulary_items,
    vocabulary_translations,
)
from app.repositories.postgres.xp import award, xp_events
from app.repositories.practice import (
    ActiveSessionLimitReachedError,
    PracticeConflictError,
    PracticeNotFoundError,
    PracticeStorageError,
)
from app.schemas.base import utc_now
from app.schemas.enums import (
    SessionStatus,
    VocabularyEncounterOutcome,
    VocabularyEncounterType,
)
from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.schemas.sessions import Session, SessionDetailResponse, SessionSummaryResponse
from app.schemas.tasks import (
    CheckVocabularyAnswerResponse,
    SessionProgress,
    SessionTask,
    SessionTaskPublic,
    TaskActionResponse,
    TaskAttempt,
)
from app.schemas.translation import SceneTranslationResult
from app.schemas.vocabulary import (
    VocabularyEncounter,
    VocabularyItem,
    VocabularyTranslation,
)
from app.services.background import InlineBackgroundRunner
from app.services.scene_analysis import DeterministicSceneAnalyzer
from app.services.session_plan import (
    bootstrap_word,
    build_grammar_lessons,
    build_ispy_clue_tasks,
    build_ispy_description_tasks,
    build_tasks,
)

logger = logging.getLogger(__name__)

TERMINAL = {"completed", "abandoned", "failed"}
MAX_ACTIVE_SESSIONS = 3
ALLOWED_TRANSITIONS = {
    "created": {"analyzingScene", "abandoned", "failed"},
    "analyzingScene": {"awaitingObjectReview", "abandoned", "failed"},
    "awaitingObjectReview": {"analyzingScene", "generatingTasks", "abandoned", "failed"},
    "generatingTasks": {"awaitingObjectReview", "ready", "inProgress", "abandoned", "failed"},
    "ready": {"inProgress", "abandoned", "failed"},
    "inProgress": {"completed", "abandoned", "failed"},
    "completed": set(),
    "abandoned": set(),
    "failed": set(),
}
READ_TASKS = {"vocabularyIntroduction", "grammarExplanation", "syntaxExplanation"}
ANALYSIS_TIMEOUT = timedelta(minutes=15)


def _normalize_answer(value):
    return " ".join(value.casefold().strip().split()).rstrip(".!?\u3002")


def _lesson_answer_is_correct(task, question_id, answer):
    question = next(
        item for item in task.public_content.questions if item.question_id == question_id
    )
    expected = task.answer_key.correct_option_ids.get(question_id)
    return (
        _normalize_answer(answer) == _normalize_answer(expected)
        if getattr(question, "interaction_type", "multipleChoice") == "sentenceBuilding"
        else answer == expected
    )


def task_progress(tasks):
    complete = sum(t.status == "completed" for t in tasks)
    skipped = sum(t.status == "skipped" for t in tasks)
    return SessionProgress(
        completed_task_count=complete,
        skipped_task_count=skipped,
        terminal_task_count=complete + skipped,
        total_task_count=len(tasks),
    )


def _learning_task_payload(translation_payload, translated_scene, scene_relations=()):
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


def _ispy_clue_payload(translation_payload, translated_scene, objects, scene_relations=()):
    """Give the clue model translated scene facts and positions, never the image itself."""
    payload = _learning_task_payload(translation_payload, translated_scene, scene_relations)
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
    payload = _ispy_clue_payload(
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


@dataclass(frozen=True)
class DescriptionClaim:
    """The target-blind inputs of a claimed I-Spy description attempt."""

    task_id: UUID
    attempt_id: UUID
    context: dict
    learner_text: str
    session_id: str


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
            self._analyzer = (
                RoutedSceneAnalyzer(deterministic, uploaded) if uploaded else deterministic
            )
        return self._analyzer

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
        return session.model_copy(update={**values, "status": SessionStatus(target)})

    def _tasks(self, c, session_id):
        return [
            SessionTask.model_validate(dict(r))
            for r in c.execute(
                select(session_tasks)
                .where(session_tasks.c.session_id == session_id)
                .order_by(session_tasks.c.order_index)
            ).mappings()
        ]

    def check_vocabulary_answer(self, task_id, question_id, option_id):
        """Evaluate one vocabulary choice without recording or completing the task."""
        with self.read_connection() as c:
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
                raise PracticeConflictError("This task does not support answer checking.")
            question = next(
                (item for item in task.public_content.questions if item.question_id == question_id),
                None,
            )
            if question is None or option_id not in {item.option_id for item in question.options}:
                raise PracticeConflictError("Choose one of the offered answers.")
            correct_option_id = task.answer_key.correct_option_ids.get(question_id)
            if correct_option_id is None:
                raise PracticeConflictError("This question has no answer key.")
            return CheckVocabularyAnswerResponse(
                question_id=question_id,
                is_correct=correct_option_id == option_id,
                correct_option_id=correct_option_id,
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

    def _detail(self, c, session):
        asset, scene = self._scene_media(c, session)
        objects, relations = self._scene_objects(c, session)
        words, translations = self._vocabulary(c, session, objects)
        draft = session.analysis_draft
        tasks = self._tasks(c, session.id)
        return SessionDetailResponse(
            session=session,
            media_asset=asset,
            scene_id=scene["slug"] if scene else None,
            title=_scene_title(session, scene),
            analysis_mode=None if asset.source == "preloaded" else "placeholder",
            scene_objects=objects,
            scene_object_relations=relations,
            vocabulary=words,
            translations=translations,
            translation_preview=(draft or {}).get("translationPreview"),
            tasks=[SessionTaskPublic.from_internal(t) for t in tasks],
            progress=task_progress(tasks),
            next_task_id=next(
                (t.id for t in tasks if t.status not in {"completed", "skipped"}), None
            ),
        )

    def _active_row(self, c, profile_id):
        return (
            c.execute(
                select(
                    sessions,
                    _stale_processing().label("is_stale"),
                )
                .where(
                    sessions.c.user_id == self.user_id,
                    sessions.c.language_profile_id == profile_id,
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

    def active(self, profile_id):
        try:
            with self.read_connection() as c:
                if (
                    c.execute(
                        select(users.c.id).where(users.c.id == self.user_id)
                    ).scalar_one_or_none()
                    is None
                ):
                    return None
                row = self._active_row(c, profile_id)
                if row is None:
                    return None
                if not row["is_stale"]:
                    return self._detail(c, parse_session(row))
            # Only an expired processing session needs the write path.
            with self.transaction() as c:
                self._reap(c, profile_id)
                row = self._active_row(c, profile_id)
                return self._detail(c, parse_session(row)) if row else None
        except PracticeNotFoundError:
            return None

    def create(self, request):
        with self.transaction() as c:
            profile = (
                c.execute(
                    select(language_profiles).where(
                        language_profiles.c.id == request.language_profile_id,
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
                c.execute(select(media_assets).where(media_assets.c.id == request.media_asset_id))
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
                        func.lower(preloaded_scenes.c.language_code)
                        == profile["target_language_code"].lower(),
                    )
                ).first()
                is None
            ):
                raise PracticeNotFoundError("Scene not found for this language.")
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
                    if existing["scene_media_asset_id"] != request.media_asset_id:
                        raise PracticeConflictError("This request key was used for another image.")
                    return self._detail(c, parse_session(existing))
            self._reap(c, request.language_profile_id)
            # Re-selecting an image resumes its unfinished session, but an
            # unfinished session for another image must never block a learner
            # from starting a new one.
            existing = (
                c.execute(
                    select(sessions).where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.language_profile_id == request.language_profile_id,
                        sessions.c.scene_media_asset_id == request.media_asset_id,
                        sessions.c.status.not_in(TERMINAL),
                    )
                    .order_by(sessions.c.started_at.desc().nulls_last(), sessions.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._detail(c, parse_session(existing))
            active_count = c.execute(
                select(func.count()).select_from(sessions).where(
                    sessions.c.user_id == self.user_id,
                    sessions.c.language_profile_id == request.language_profile_id,
                    sessions.c.status.not_in(TERMINAL),
                )
            ).scalar_one()
            if active_count >= MAX_ACTIVE_SESSIONS:
                raise ActiveSessionLimitReachedError(
                    "You can keep up to three unfinished practices open at once. "
                    "Finish or leave one before starting another."
                )
            session = Session(
                user_id=self.user_id,
                language_profile_id=request.language_profile_id,
                scene_media_asset_id=request.media_asset_id,
                idempotency_key=request.idempotency_key,
            )
            c.execute(insert(sessions).values(**session.model_dump(by_alias=False)))
            return self._detail(c, session)

    def _expire_stale(self, c, *scope):
        """Fail stale processing sessions inside `scope` with their status's code."""
        for status, failure_code in PROCESSING_FAILURE_CODES.items():
            c.execute(
                update(sessions)
                .where(*scope, _stale_processing(status))
                .values(status="failed", failure_code=failure_code)
            )

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
            if session.status in TERMINAL:
                raise PracticeConflictError("Cannot analyze a terminal session.")
            if session.status in {"ready", "inProgress"}:
                raise PracticeConflictError("Session analysis is already finished.")
            if session.status != "created":
                # analyzingScene/awaitingObjectReview/generatingTasks: never re-run the model.
                return self._detail(c, session)
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
            claimed = self._transition(c, session, "analyzingScene")
            detail = self._detail(c, claimed)
        if asset.source == "preloaded":
            # Curated scenes already have their objects, marker positions,
            # attributes and relations saved. Set up the fresh learner session
            # on this request instead of showing the uploaded-photo animation.
            self._run_scene_analysis(
                session_id, profile_id, claimed, asset, dict(profile), dict(scene)
            )
            return self.get(session_id, profile_id)
        self.background.submit(
            self._run_scene_analysis,
            session_id,
            profile_id,
            claimed,
            asset,
            dict(profile),
            dict(scene) if scene else None,
        )
        return detail

    def _run_scene_analysis(self, session_id, profile_id, claimed, asset, profile, scene):
        """Model round-trip, off the request path. Must never raise to its runner."""
        try:
            result = self.analyzer.analyze(
                claimed, asset, profile, scene
            )
            with self.transaction() as c:
                current = self._session(c, session_id, profile_id)
                if current.status != "analyzingScene":
                    return
                self._transition(
                    c,
                    current,
                    "awaitingObjectReview",
                    session_title=result.title,
                    session_summary=result.summary,
                    analysis_draft={
                        "objects": [
                            obj.model_dump(mode="json", by_alias=False)
                            for obj in result.objects
                        ],
                        "relations": [
                            row.model_dump(mode="json", by_alias=False)
                            for row in result.relations
                        ],
                    },
                )
        except Exception as error:
            logger.exception("Scene analysis failed for session %s.", session_id)
            try:
                # Compare by value: the enum is a StrEnum and importing the
                # scene-analysis feature here would create an import cycle.
                failure_code = (
                    "imageModerationFailed"
                    if getattr(error, "code", None) == "imageModerationFailed"
                    else "sceneAnalysisFailed"
                )
                with self.transaction() as c:
                    current = self._session(c, session_id)
                    if current.status == "analyzingScene":
                        self._transition(
                            c, current, "failed", failure_code=failure_code
                        )
            except Exception:
                logger.exception(
                    "Could not record the analysis failure for session %s.", session_id
                )

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
            self._session(c, session_id, profile_id)
            profile = (
                c.execute(select(language_profiles).where(language_profiles.c.id == profile_id))
                .mappings()
                .one()
            )
            self._catalog_word(c, profile, label)
            return {"available": True}

    def review(self, session_id, profile_id, request):
        detail = self._review(session_id, profile_id, request)
        self.background.submit(self._run_task_generation, session_id, profile_id)
        return detail

    def _run_task_generation(self, session_id, profile_id):
        """Translator + lesson generation, off the request path. Never re-raises."""
        revision = None
        try:
            claim = self._claim_generation(session_id, profile_id)
            if claim is None:
                return
            revision = claim.revision
            self._generate_tasks(claim)
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
            positions = {item.id: item.anchor_point for item in request.repositioned_objects}
            for object_id in request.accepted_object_ids:
                obj = existing[object_id].model_copy(
                    update={
                        "attributes": request.object_attributes.get(object_id) or None,
                        "anchor_point": positions.get(object_id, existing[object_id].anchor_point),
                    }
                )
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
                    bounding_box={"x": added.x, "y": added.y, "width": 0.01, "height": 0.01},
                    attributes=request.object_attributes.get(added.id) or None,
                )
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
            _asset, scene = self._scene_media(c, session)
            objects, relations = self._scene_objects(c, session)
            return GenerationClaim(
                session_id,
                profile_id,
                revision,
                session,
                dict(profile),
                _scene_title(session, scene),
                objects,
                relations,
            )

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
        ispy_descriptions = []
        introduction_id = None
        objects, relations = list(claim.objects), claim.relations
        if self.translator:
            payload = {
                "targetLanguage": profile["target_language_code"],
                "sceneTitle": claim.title,
                "sceneSummary": session.session_summary or "Confirmed scene vocabulary.",
                "objects": [
                    {"key": str(obj.id), "source": obj.label} for obj in objects
                ],
                "attributes": [
                    {
                        "key": f"{obj.id}:{attribute_type}",
                        "source": value,
                    }
                    for obj in objects
                    for attribute_type, value in (obj.attributes or {}).items()
                    if isinstance(value, str) and value.strip()
                ],
                "relationships": [
                    {"key": str(row.id), "source": row.relation}
                    for row in relations
                ],
            }
            with _timed("translation", session_id):
                translated_scene = self.translator.translate(payload)

        # Checkpoint: commit translations and task 1 before the slower lesson
        # and clue calls, so the learner can start while tasks are built.
        with self.transaction() as c:
            session = self._current_generation(c, claim)
            if session is None:
                return
            # Rebuild tasks from scratch for the accepted objects.
            c.execute(delete(session_tasks).where(session_tasks.c.session_id == session_id))
            if self.translator:
                draft = {
                    **(session.analysis_draft or {}),
                    "translationPreview": translated_scene.model_dump(
                        mode="json", by_alias=True
                    ),
                }
                c.execute(
                    update(sessions).where(sessions.c.id == session.id)
                    .values(analysis_draft=draft)
                )
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
            objects, relations = self._scene_objects(c, session)
            vocabulary, vocabulary_translations = self._vocabulary(c, session, objects)
            words_by_id = {word.id: word for word in vocabulary}
            translations_by_id = {
                word.vocabulary_item_id: word for word in vocabulary_translations
            }
            if any(
                obj.vocabulary_item_id not in words_by_id
                or obj.vocabulary_item_id not in translations_by_id
                for obj in objects
            ):
                raise PracticeConflictError("Every selected object needs a word and translation.")
            words = [words_by_id[obj.vocabulary_item_id] for obj in objects]
            translations = [translations_by_id[obj.vocabulary_item_id] for obj in objects]
            rebuilt = build_tasks(
                session_id,
                objects,
                words,
                translations,
                False,
                translated_scene if self.translator else _translation_preview(session),
            )
            introduction = next(
                task for task in rebuilt if task.kind == "vocabularyIntroduction"
            )
            introduction.order_index = 0
            c.execute(insert(session_tasks).values(**entity_values(introduction)))
            introduction_id = introduction.id
            if self.translator:
                # Translation is the moment a learner has collected these
                # words. Persist a "new" vocabulary record now, rather than
                # waiting for task completion, so leaving the lesson does not
                # discard their image vocabulary.
                for word in words:
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

        if self.translator:
            lessons, ispy_clues = self._lessons_and_clues(
                session_id, payload, translated_scene, objects, words, relations
            )
            if self.ispy_guess_generator:
                ispy_descriptions = build_ispy_description_tasks(
                    session_id, objects, words,
                    _ispy_guess_context(
                        payload, translated_scene, objects, relations
                    ),
                )

        with self.transaction() as c:
            session = self._current_generation(c, claim)
            if session is None:
                return
            learning = [
                task for task in rebuilt if task.kind not in {"ispyRound", "reflection"}
            ]
            clues = ispy_clues or [task for task in rebuilt if task.kind == "ispyRound"]
            descriptions = ispy_descriptions or [
                task for task in rebuilt if task.kind == "reflection"
            ]
            if lessons:
                # Generated lessons replace deterministic grammar/syntax exercises.
                learning = [
                    task for task in learning if task.kind == "vocabularyIntroduction"
                ] + lessons
            rebuilt = [*learning, *clues, *descriptions]
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

    def _lessons(self, session_id, payload, translated_scene, relations):
        if not self.learning_task_generator:
            return []
        try:
            with _timed("learning-task generation", session_id):
                return build_grammar_lessons(
                    session_id,
                    self.learning_task_generator.generate(
                        _learning_task_payload(payload, translated_scene, relations)
                    ),
                )
        except Exception:
            logger.exception(
                "Learning-task generation failed for session %s; "
                "using the deterministic lesson plan.", session_id,
            )
            return []

    def _clues(self, session_id, payload, translated_scene, objects, words, relations):
        if not self.ispy_clue_generator:
            return []
        try:
            with _timed("I-Spy clue generation", session_id):
                return build_ispy_clue_tasks(
                    session_id,
                    self.ispy_clue_generator.generate(
                        _ispy_clue_payload(payload, translated_scene, objects, relations)
                    ),
                    objects, words,
                )
        except ISpyClueGenerationError:
            logger.exception("I-Spy clue generation failed for session %s.", session_id)
            return []

    def _lessons_and_clues(self, session_id, payload, translated_scene, objects, words, relations):
        """Run the two independent generation calls at once, each with its own fallback.

        The clue call runs on a one-thread executor owned by this job rather than
        the shared background pool, so each job adds at most one thread and a
        saturated pool cannot deadlock waiting on itself.
        """
        lessons = partial(self._lessons, session_id, payload, translated_scene, relations)
        clues = partial(
            self._clues, session_id, payload, translated_scene, objects, words, relations
        )
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
            if not abandon and (
                session.status == "generatingTasks"
                or not tasks or any(t.status not in {"completed", "skipped"} for t in tasks)
            ):
                raise PracticeConflictError("Complete or skip every task first.")
            session = self._transition(c, session, target)
            if not abandon:
                award(
                    c,
                    user_id=self.user_id,
                    event_type="sessionCompleted",
                    idempotency_key=f"session:{session.id}",
                    language_profile_id=session.language_profile_id,
                    session_id=session.id,
                )
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
                xp_earned=c.execute(
                    select(func.coalesce(func.sum(xp_events.c.amount), 0))
                    .select_from(xp_events)
                    .where(
                        xp_events.c.session_id == session.id,
                        xp_events.c.user_id == self.user_id,
                    )
                ).scalar_one(),
                **self._ispy_summary(c, session.id),
            )

    def _ispy_summary(self, c, session_id):
        outcomes = (
            c.execute(
                select(task_attempts.c.is_correct)
                .join(session_tasks, session_tasks.c.id == task_attempts.c.session_task_id)
                .where(
                    session_tasks.c.session_id == session_id, session_tasks.c.phase == "ispy"
                )
            )
            .scalars()
            .all()
        )
        return {
            "ispy_correct_count": sum(outcome is True for outcome in outcomes),
            "ispy_attempt_count": sum(outcome is not None for outcome in outcomes),
        }

    def _encounter(
        self, c, task, event_id, outcome, introduced=False, vocabulary_item_id=None
    ):
        explicit_vocabulary_item_id = vocabulary_item_id
        resolved_vocabulary_item_id = vocabulary_item_id or task.vocabulary_item_id
        if not resolved_vocabulary_item_id:
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
                .join(
                    language_profiles, language_profiles.c.id == sessions.c.language_profile_id
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
        return SessionTask.model_validate(dict(row))

    def _evaluates_description(self, task):
        return bool(
            task.kind == "reflection"
            and task.answer_key
            and task.answer_key.scene_description_context
            and self.ispy_guess_generator
        )

    def _claim_description(self, task_id, request):
        """Claim a model-graded I-Spy attempt; ``None`` when no model call is due.

        Saved attempts, inactive tasks and invalid input fall through to
        ``_apply_task_action``, which returns or rejects them.
        """
        with self.transaction() as c:
            task = self._task_row(c, task_id)
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
            c.execute(
                update(task_evaluation_claims)
                .where(task_evaluation_claims.c.id == task.id)
                .values(evaluation_claim_id=attempt_id)
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

    def task_action(self, task_id, action, request=None):
        """Claim → model call with no transaction open → persist if still claimed."""
        evaluation = None
        if action == "attempt":
            claim = self._claim_description(task_id, request)
            if claim is not None:
                evaluation = DescriptionEvaluation(
                    claim.attempt_id, self._evaluate_description(claim)
                )
        return self._apply_task_action(task_id, action, request, evaluation)

    def _apply_task_action(self, task_id, action, request, evaluation):
        with self.transaction() as c:
            task = self._task_row(c, task_id)
            session = self._session(c, task.session_id)
            attempt = None
            if action == "attempt":
                payload = request.model_dump(
                    mode="json", by_alias=False, exclude={"idempotency_key"}
                )
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
                    "completed", "skipped"
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
                        self._encounter(c, task, task.id, "completed", introduced=True)
                elif action == "attempt":
                    evaluation_details = None
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
                        guess = evaluation.guess
                        if guess is None:
                            correct = None
                            feedback_message = "Your description was saved. Keep using scene words."
                        else:
                            correct = guess.guessed_object_key == str(task.scene_object_id)
                            feedback_message = guess.feedback
                            evaluation_details = guess.model_dump(mode="json", by_alias=True)
                    else:
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
                        evaluation_details = {
                            "questionResults": question_results,
                            "correctAnswers": correct_answers,
                        }
                        feedback_message = (
                            f"{correct_count} of {len(question_results)} questions correct."
                        )
                    attempt = TaskAttempt(
                        id=attempt_id,
                        session_task_id=task.id,
                        attempt_number=1,
                        input_mode=request.input_mode,
                        response_payload=payload,
                        is_correct=correct,
                        score=None if correct is None else int(correct),
                        feedback={"message": feedback_message},
                        evaluation_details=evaluation_details,
                    )
                    c.execute(insert(task_attempts).values(**entity_values(attempt)))
                    if evaluation is not None:
                        c.execute(
                            update(task_evaluation_claims)
                            .where(task_evaluation_claims.c.id == task.id)
                            .values(evaluation_claim_id=None)
                        )
                    if correct is True and task.phase == "ispy":
                        award(
                            c,
                            user_id=self.user_id,
                            event_type="ispyCorrect",
                            idempotency_key=f"attempt:{attempt.id}",
                            language_profile_id=session.language_profile_id,
                            session_id=task.session_id,
                        )
                    self._encounter(
                        c,
                        task,
                        attempt.id,
                        "completed" if correct is None else ("correct" if correct else "incorrect"),
                    )
                    if task.kind == "vocabularyIntroduction" and task.public_content.words:
                        for learning_word in task.public_content.words:
                            self._encounter(
                                c,
                                task,
                                attempt.id,
                                "correct" if correct else "incorrect",
                                introduced=True,
                                vocabulary_item_id=learning_word.vocabulary_item_id,
                            )
                    values = dict(
                        status="completed",
                        completed_at=utc_now(),
                        started_at=task.started_at or utc_now(),
                    )
                else:
                    raise PracticeConflictError("Unknown task action.")
                c.execute(
                    update(session_tasks).where(session_tasks.c.id == task.id).values(**values)
                )
                if values["status"] == "completed":
                    award(
                        c,
                        user_id=self.user_id,
                        event_type="taskCompleted",
                        idempotency_key=f"task:{task.id}",
                        language_profile_id=session.language_profile_id,
                        session_id=task.session_id,
                    )
            tasks = self._tasks(c, task.session_id)
            return TaskActionResponse(
                task=SessionTaskPublic.from_internal(next(t for t in tasks if t.id == task.id)),
                attempt=attempt,
                next_task_id=next(
                    (t.id for t in tasks if t.status not in {"completed", "skipped"}), None
                ),
                session_progress=task_progress(tasks),
            )


def _attempt_id(task, request):
    return uuid5(task.id, "attempt:" + (request.idempotency_key or "single-evaluation"))


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
            for question_id, answer in request.answers.items()
            for question in [questions_by_id[question_id]]
        ):
            raise PracticeConflictError("Select only choices offered by this lesson.")
        if not set(request.typed_answers).issubset(
            key.accepted_text_answers_by_vocabulary_id
        ):
            raise PracticeConflictError("Typing practice contains an unknown word.")
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

    return _normalize_answer(request.text) in {
        _normalize_answer(answer) for answer in key.accepted_text_answers
    }
