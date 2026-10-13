"""Standalone I-Spy games played over a fixed snapshot of a confirmed scene.

A game is a session with mode ``ispy``. Starting one copies the user's most
recently confirmed lesson scene for the photo (or, for a preloaded scene the
user has not reviewed, its curated facts) into game-scoped scene records, then
generates only I-Spy clue and description rounds from that snapshot.
"""

import base64
import binascii
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import and_, delete, exists, func, insert, or_, select, tuple_, update

from app.ai.features.translation.schemas import SceneTranslationResult
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scene_objects import (
    object_values,
    scene_object_relations,
    scene_objects,
)
from app.repositories.postgres.scenes import preloaded_scenes
from app.repositories.postgres.tasks import entity_values, session_tasks
from app.repositories.postgres.workflow import (
    TERMINAL,
    _ispy_guess_context,
    parse_session,
    translation_payload,
)
from app.repositories.practice import PracticeConflictError
from app.schemas.base import utc_now
from app.schemas.enums import SessionMode, SessionStatus
from app.schemas.ispy import ISpyPhoto, ISpyPhotoPage
from app.schemas.media import MediaAsset
from app.schemas.sessions import Session
from app.services.scene_analysis import curated_relations
from app.services.session_plan import build_ispy_description_tasks, build_objects

CONFIRM_SCENE_FIRST = (
    "Confirm this photo's scene review in a lesson first, then play I-Spy with it."
)
PHOTO_PAGE_SIZE = 12
UNCONFIRMED_STATUSES = ("created", "analyzingScene", "awaitingObjectReview")


class ISpyGameUnavailableError(Exception):
    """The confirmed scene could not produce any I-Spy round."""


def confirmed_lessons(user_id):
    """Lesson sessions of ``user_id`` whose reviewed scene facts are saved."""
    return and_(
        sessions.c.user_id == user_id,
        sessions.c.mode == SessionMode.LESSON,
        sessions.c.scene_confirmed_at.is_not(None),
        sessions.c.status.not_in(UNCONFIRMED_STATUSES),
    )


def encode_cursor(created_at: datetime, asset_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{asset_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        created_at, asset_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created_at), UUID(asset_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise PracticeConflictError("This photo list is out of date. Reload it.") from exc


def remap_translation(preview, expected):
    """``preview`` rekeyed to the snapshot, or ``None`` unless it covers ``expected`` exactly.

    ``preview`` carries the source session's translated terms with their keys
    already mapped to snapshot IDs; ``expected`` is the snapshot's own
    translation payload.
    """
    remapped = {}
    for kind in ("objects", "attributes", "relationships"):
        wanted = {term["key"]: term["source"] for term in expected[kind]}
        terms = [term for term in preview.get(kind, []) if term.get("key") in wanted]
        if (
            len(terms) != len(wanted)
            or {term["key"] for term in terms} != set(wanted)
            or any(term.get("source") != wanted[term["key"]] for term in terms)
        ):
            return None
        remapped[kind] = terms
    return SceneTranslationResult.model_validate(remapped)


class PostgresISpyGameRepository:
    def __init__(self, workflow):
        self.workflow = workflow
        self.user_id = workflow.user_id

    def photos(self, cursor=None, limit=PHOTO_PAGE_SIZE):
        """The user's own practice photos, newest first, once per media asset.

        Photos whose only lessons failed before review are left out: they can
        never gain confirmed facts.
        """
        confirmed_at = (
            select(func.max(sessions.c.scene_confirmed_at))
            .where(
                confirmed_lessons(self.user_id),
                sessions.c.scene_media_asset_id == media_assets.c.id,
            )
            .scalar_subquery()
        )
        query = (
            select(media_assets, confirmed_at.label("confirmed_at"))
            .where(
                media_assets.c.owner_user_id == self.user_id,
                media_assets.c.source.in_(["camera", "userUpload"]),
                media_assets.c.media_type == "image",
                exists().where(
                    sessions.c.user_id == self.user_id,
                    sessions.c.mode == SessionMode.LESSON,
                    sessions.c.scene_media_asset_id == media_assets.c.id,
                    or_(
                        sessions.c.status != "failed",
                        sessions.c.scene_confirmed_at.is_not(None),
                    ),
                ),
            )
            .order_by(media_assets.c.created_at.desc(), media_assets.c.id.desc())
            .limit(limit + 1)
        )
        if cursor:
            query = query.where(
                tuple_(media_assets.c.created_at, media_assets.c.id) < decode_cursor(cursor)
            )
        asset_columns = {column.key for column in media_assets.c}
        with self.workflow.read_connection() as c:
            rows = c.execute(query).mappings().all()
        photos = [
            ISpyPhoto(
                media_asset=MediaAsset.model_validate(
                    {key: row[key] for key in asset_columns}
                ),
                playable=row["confirmed_at"] is not None,
                confirmed_at=row["confirmed_at"],
            )
            for row in rows[:limit]
        ]
        next_cursor = (
            encode_cursor(photos[-1].media_asset.created_at, photos[-1].media_asset.id)
            if len(rows) > limit
            else None
        )
        return ISpyPhotoPage(photos=photos, next_cursor=next_cursor)

    def active(self, profile_id):
        return self.workflow.active(profile_id, SessionMode.ISPY)

    def start(self, request):
        workflow = self.workflow
        profile_id = request.language_profile_id
        with workflow.transaction() as c:
            profile, asset = workflow._practice_media(c, profile_id, request.media_asset_id)
            existing = (
                c.execute(
                    select(sessions).where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.language_profile_id == profile_id,
                        sessions.c.idempotency_key == request.idempotency_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                if (
                    existing["scene_media_asset_id"] != request.media_asset_id
                    or existing["mode"] != SessionMode.ISPY
                ):
                    raise PracticeConflictError("This request key was used for another game.")
                return workflow._detail(c, parse_session(existing))
            workflow._reap(c, profile_id)
            unfinished = (
                c.execute(
                    select(sessions)
                    .where(
                        sessions.c.user_id == self.user_id,
                        sessions.c.language_profile_id == profile_id,
                        sessions.c.scene_media_asset_id == request.media_asset_id,
                        sessions.c.mode == SessionMode.ISPY,
                        sessions.c.status.not_in(TERMINAL),
                    )
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if unfinished is not None:
                return workflow._detail(c, parse_session(unfinished))
            workflow._check_active_limit(c, profile_id, SessionMode.ISPY)
            source = self._source(c, request.media_asset_id)
            scene = None
            if source is None:
                if asset["source"] != "preloaded":
                    raise PracticeConflictError(CONFIRM_SCENE_FIRST)
                scene = self._curated_scene(c, asset["id"], profile)
            game = Session(
                user_id=self.user_id,
                language_profile_id=profile_id,
                scene_media_asset_id=request.media_asset_id,
                mode=SessionMode.ISPY,
                status=SessionStatus.GENERATING_TASKS,
                source_session_id=source["id"] if source else None,
                idempotency_key=request.idempotency_key,
                session_title=source["session_title"] if source else scene["title"],
                session_summary=(
                    source["session_summary"] if source else scene.get("description")
                ),
                analysis_draft={"processingStartedAt": utc_now().isoformat()},
            )
            c.execute(insert(sessions).values(**game.model_dump(by_alias=False)))
            if source:
                game = self._copy_confirmed_scene(c, source, game, profile)
            else:
                self._copy_curated_scene(
                    c, game, MediaAsset.model_validate(dict(asset)), profile, scene
                )
            detail = workflow._detail(c, game)
        workflow.background.submit(
            workflow._run_task_generation, game.id, profile_id, self._generate
        )
        return detail

    def _source(self, c, asset_id):
        """The user's most recently confirmed lesson scene for ``asset_id``."""
        return (
            c.execute(
                select(
                    sessions,
                    language_profiles.c.target_language_code,
                    language_profiles.c.source_language_code,
                )
                .join(language_profiles, language_profiles.c.id == sessions.c.language_profile_id)
                .where(confirmed_lessons(self.user_id), sessions.c.scene_media_asset_id == asset_id)
                .order_by(sessions.c.scene_confirmed_at.desc(), sessions.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )

    def _curated_scene(self, c, asset_id, profile):
        return dict(
            c.execute(
                select(preloaded_scenes).where(
                    preloaded_scenes.c.media_asset_id == asset_id,
                    preloaded_scenes.c.is_active.is_(True),
                    func.lower(preloaded_scenes.c.language_code)
                    == profile["target_language_code"].lower(),
                )
            )
            .mappings()
            .first()
        )

    def _copy_confirmed_scene(self, c, source_row, game, profile):
        """Copy the source session's saved objects and relations under fresh game IDs."""
        source = parse_session(source_row)
        objects, relations = self.workflow._scene_objects(c, source)
        if not objects:
            raise PracticeConflictError(CONFIRM_SCENE_FIRST)
        same_languages = all(
            source_row[field].lower() == profile[field].lower()
            for field in ("target_language_code", "source_language_code")
        )
        object_ids = {obj.id: uuid5(game.id, f"snapshot:{obj.id}") for obj in objects}
        relation_ids = {row.id: uuid5(game.id, f"snapshot-relation:{row.id}") for row in relations}
        copies = [
            obj.model_copy(
                update={
                    "id": object_ids[obj.id],
                    "session_id": game.id,
                    "vocabulary_item_id": obj.vocabulary_item_id if same_languages else None,
                }
            )
            for obj in objects
        ]
        relation_copies = [
            row.model_copy(
                update={
                    "id": relation_ids[row.id],
                    "subject_scene_object_id": object_ids[row.subject_scene_object_id],
                    "reference_scene_object_id": object_ids[row.reference_scene_object_id],
                }
            )
            for row in relations
        ]
        for obj in copies:
            c.execute(insert(scene_objects).values(**object_values(obj)))
        for row in relation_copies:
            c.execute(insert(scene_object_relations).values(**row.model_dump(by_alias=False)))
        preview = (source.analysis_draft or {}).get("translationPreview")
        if not (same_languages and preview and all(obj.vocabulary_item_id for obj in copies)):
            return game
        keys = {str(old): str(new) for old, new in (object_ids | relation_ids).items()}
        rekeyed = {
            "objects": [
                {**term, "key": keys.get(term["key"], term["key"])}
                for term in preview.get("objects", [])
            ],
            "attributes": [
                {**term, "key": _rekey_attribute(term["key"], keys)}
                for term in preview.get("attributes", [])
            ],
            "relationships": [
                {**term, "key": keys.get(term["key"], term["key"])}
                for term in preview.get("relationships", [])
            ],
        }
        translated = remap_translation(
            rekeyed,
            translation_payload(
                profile["target_language_code"], "", "", copies, relation_copies
            ),
        )
        if translated is None:
            return game
        draft = {
            **game.analysis_draft,
            "translationPreview": translated.model_dump(mode="json", by_alias=True),
        }
        c.execute(update(sessions).where(sessions.c.id == game.id).values(analysis_draft=draft))
        return game.model_copy(update={"analysis_draft": draft})

    def _copy_curated_scene(self, c, game, asset, profile, scene):
        objects, _, _ = build_objects(c, game, asset, profile, scene)
        for obj in objects:
            c.execute(insert(scene_objects).values(**object_values(obj)))
        for row in curated_relations(scene, objects):
            c.execute(insert(scene_object_relations).values(**row.model_dump(by_alias=False)))

    def _generate(self, claim):
        """Translate if needed, then build only I-Spy rounds from the snapshot.

        Like lesson generation, model calls run with no transaction open and
        every write first checks that ``claim`` is still current.
        """
        workflow = self.workflow
        session, profile = claim.session, claim.profile
        objects, relations = list(claim.objects), claim.relations
        payload = translation_payload(
            profile["target_language_code"],
            claim.title,
            session.session_summary or "Confirmed scene vocabulary.",
            objects,
            relations,
        )
        preview = (session.analysis_draft or {}).get("translationPreview")
        if preview:
            translated_scene = SceneTranslationResult.model_validate(preview)
        elif workflow.translator:
            translated_scene = workflow.translator.translate(payload, **claim.generation_options)
        else:
            raise ISpyGameUnavailableError("No translator is configured.")
        with workflow.transaction() as c:
            current = workflow._current_generation(c, claim)
            if current is None:
                return
            if not preview:
                workflow._store_translation(c, current, profile, objects, translated_scene)
            objects, relations = workflow._scene_objects(c, current)
            words, _translations = workflow._words(c, current, objects)
        clues = workflow._clues(
            session.id, payload, translated_scene, objects, words, relations,
            claim.generation_options,
        )
        if not clues:
            raise ISpyGameUnavailableError("No I-Spy clue rounds were generated.")
        descriptions = (
            build_ispy_description_tasks(
                session.id, objects, words,
                _ispy_guess_context(payload, translated_scene, objects, relations),
            )
            if workflow.ispy_guess_generator
            else []
        )
        with workflow.transaction() as c:
            current = workflow._current_generation(c, claim)
            if current is None:
                return
            c.execute(delete(session_tasks).where(session_tasks.c.session_id == session.id))
            for index, task in enumerate([*clues, *descriptions]):
                task.order_index = index
                c.execute(insert(session_tasks).values(**entity_values(task)))
            workflow._transition(c, current, "inProgress")


def _rekey_attribute(key, keys):
    object_key, _, attribute = key.partition(":")
    return f"{keys.get(object_key, object_key)}:{attribute}"
