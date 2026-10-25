"""Private uploaded-room preparation; owns no sessions or database writes."""

import copy
import hashlib
from typing import Annotated
from uuid import UUID

from pydantic import Field, ValidationError, field_validator, model_validator

from app.ai.cache import CacheScope
from app.ai.contracts import VisionImage
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.features.translation.schemas import SceneTranslationResult
from app.ai.features.translation.validation import (
    normalize_object_articles,
    validate_translation_terms,
)
from app.schemas.base import ApiModel
from app.schemas.enums import MediaSource, MediaType, SceneRelationType
from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.schemas.sessions import Session
from app.services.room_clues import RoomClueError, build_room_pack
from app.services.room_languages import room_profile_supported
from app.services.scene_analysis import SceneAnalysisResult


class RoomPhotoError(ValueError):
    """Safe actionable room errors; provider bodies and image bytes stay private."""

    def __init__(self, code: str, message: str, *, retryable: bool = True):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class RoomPhotoObject(ApiModel):
    key: UUID
    label: Annotated[str, Field(min_length=1, max_length=100)]
    x: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    color: Annotated[str, Field(min_length=1, max_length=40)] | None = None

    @field_validator("color", mode="before")
    @classmethod
    def empty_colour_is_unknown(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class RoomPhotoRelation(ApiModel):
    key: UUID
    subject_object_key: UUID
    relation: SceneRelationType
    reference_object_key: UUID

    @model_validator(mode="after")
    def different_endpoints(self):
        if self.subject_object_key == self.reference_object_key:
            raise ValueError("A relationship must connect different objects.")
        return self


class RoomPhotoReview(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    objects: Annotated[list[RoomPhotoObject], Field(min_length=2, max_length=6)]
    relations: Annotated[list[RoomPhotoRelation], Field(max_length=20)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def selected_facts(self):
        ids = {obj.key for obj in self.objects}
        if len(ids) != len(self.objects):
            raise ValueError("Choose each object only once.")
        seen, relation_ids = set(), set()
        for relation in self.relations:
            if not {relation.subject_object_key, relation.reference_object_key} <= ids:
                raise ValueError("Relationships must connect selected objects.")
            triple = (relation.subject_object_key, relation.relation, relation.reference_object_key)
            if triple in seen or relation.key in relation_ids:
                raise ValueError("A relationship cannot be repeated.")
            seen.add(triple)
            relation_ids.add(relation.key)
        return self


class _PhotoStorage:
    """Analyze the downloaded bytes used for duplicate hashing without a second download."""

    def __init__(self, storage_key: str, data: bytes):
        self.key, self.data = storage_key, data

    def download(self, storage_key: str) -> bytes:
        if storage_key != self.key:
            raise RoomPhotoError("room_photo_analysis_failed", "The photo changed during analysis.")
        return self.data


def _game_context(profile):
    from app.language_packs.context import game_context

    return game_context(profile)


class RoomPhotoPreparer:
    """Prepare private room photos with the runtime analyzer and translator.

    Room services own authorization, leases, bounded job retries and revisions.
    These synchronous helpers must run outside their database transactions. A
    successful analysis permits sharing; translation waits for owner confirmation.
    """

    def __init__(self, analyzer, translator, *, storage):
        self.analyzer, self.translator = analyzer, translator
        self.storage = storage

    @staticmethod
    def _language(profile: dict) -> str:
        language = str(profile.get("target_language_code", "")).lower()
        if not room_profile_supported(
            {"source_language_code": "en", **profile}, check_level=False,
        ):
            raise RoomPhotoError(
                "room_photo_unavailable",
                "Photo rooms aren't available for this learning language yet.",
                retryable=False,
            )
        return language

    def analyze(self, photo_id: UUID, owner_id: UUID, asset: MediaAsset, profile: dict) -> dict:
        self._language(profile)
        if (
            asset.owner_user_id != owner_id
            or asset.media_type is not MediaType.IMAGE
            or asset.source not in {MediaSource.USER_UPLOAD, MediaSource.CAMERA}
        ):
            raise RoomPhotoError(
                "room_photo_review_invalid", "Choose one of your uploaded photos.", retryable=False
            )
        if self.analyzer is None or self.storage is None:
            raise RoomPhotoError(
                "room_photo_unavailable",
                "Photo analysis and storage must be configured before preparing room uploads.",
            )
        try:
            image = VisionImage(
                data=self.storage.download(asset.storage_key), mime_type=asset.mime_type
            )
        except Exception as error:
            raise RoomPhotoError(
                "room_photo_analysis_failed",
                "This photo could not be opened. Try uploading it again.",
            ) from error
        # Shallow-copy only this concrete analyzer, sharing its immutable provider
        # client and grounder. Room uploads do not use the optional solo moderator;
        # the application-scoped analyzer and its solo behavior stay untouched.
        analyzer = self.analyzer
        if isinstance(analyzer, UploadedSceneAnalyzer):
            analyzer = copy.copy(analyzer)
            analyzer._storage = _PhotoStorage(asset.storage_key, image.data)
            analyzer._image_moderator = None
        identity = Session(
            id=photo_id,
            user_id=owner_id,
            language_profile_id=UUID(str(profile.get("id", photo_id))),
            scene_media_asset_id=asset.id,
        )
        try:
            result = SceneAnalysisResult.model_validate(
                analyzer.analyze(identity, asset, profile, None)
            )
            if not result.objects:
                raise ValueError("Analysis must return observed objects.")
            if len({obj.id for obj in result.objects}) != len(result.objects):
                raise ValueError("Analysis repeated an object.")
            # Friend rooms intentionally stay small even though solo mission
            # analysis can now retain a richer scene.
            room_objects = result.objects[:6]
            selected = {obj.id for obj in room_objects}
            rows = []
            for obj in room_objects:
                if obj.session_id != photo_id:
                    raise ValueError("Analysis returned an object for another photo.")
                anchor = obj.anchor_point
                if anchor:
                    x, y = float(anchor.x), float(anchor.y)
                elif obj.bounding_box:
                    box = obj.bounding_box
                    x, y = float(box.x + box.width / 2), float(box.y + box.height / 2)
                else:
                    raise ValueError("Analysis returned an object without marker coordinates.")
                attributes = obj.attributes or {}
                rows.append(
                    RoomPhotoObject(
                        key=obj.id,
                        label=obj.label,
                        x=x * 100,
                        y=y * 100,
                        color=attributes.get("color") or attributes.get("colour"),
                    )
                )
            relation_rows = []
            for relation in result.relations:
                if not {
                    relation.subject_scene_object_id,
                    relation.reference_scene_object_id,
                } <= selected:
                    continue
                relation_rows.append(
                    RoomPhotoRelation(
                        key=relation.id,
                        subject_object_key=relation.subject_scene_object_id,
                        reference_object_key=relation.reference_scene_object_id,
                        relation=relation.relation,
                    )
                )
        except Exception as error:
            raise RoomPhotoError(
                "room_photo_analysis_failed",
                "Photo analysis did not finish. Keep the photo private and try again.",
            ) from error
        return {
            "version": 1,
            "photoId": str(photo_id),
            "ownerId": str(owner_id),
            "title": result.title[:100],
            "summary": result.summary,
            "contentHash": hashlib.sha256(image.data).hexdigest(),
            "objects": [row.model_dump(mode="json", by_alias=True) for row in rows],
            "relations": [row.model_dump(mode="json", by_alias=True) for row in relation_rows],
        }

    def build_pack(
        self,
        photo_id: UUID,
        owner_id: UUID,
        profile: dict,
        analysis: dict,
        review: dict | RoomPhotoReview,
    ) -> dict:
        language = self._language(profile)
        if (
            analysis.get("photoId") != str(photo_id)
            or analysis.get("ownerId") != str(owner_id)
        ):
            raise RoomPhotoError(
                "room_photo_review_invalid",
                "Review your own analyzed photo before preparing the game.",
                retryable=False,
            )
        try:
            confirmed = RoomPhotoReview.model_validate(review)
            known = {UUID(row["key"]) for row in analysis["objects"]}
            if not {obj.key for obj in confirmed.objects} <= known:
                raise ValueError("Only objects from this photo can be reviewed.")
            room_id = UUID(str(profile["room_id"]))
        except (ValidationError, ValueError, KeyError, TypeError) as error:
            raise RoomPhotoError(
                "room_photo_review_invalid",
                "Select two to six photo objects "
                "and check their marker positions and relationships.",
                retryable=False,
            ) from error
        if self.translator is None:
            raise RoomPhotoError(
                "room_photo_unavailable",
                "Scene translation is unavailable. Please try again later.",
            )
        title = confirmed.title or str(analysis.get("title") or "Your photo")[:100]
        objects = [
            SceneObject(
                id=row.key,
                session_id=photo_id,
                label=row.label,
                anchor_point={"x": row.x / 100, "y": row.y / 100},
                attributes={"color": row.color} if row.color else None,
            )
            for row in confirmed.objects
        ]
        relations = [
            SceneObjectRelation(
                id=row.key,
                subject_scene_object_id=row.subject_object_key,
                reference_scene_object_id=row.reference_object_key,
                relation=row.relation,
            )
            for row in confirmed.relations
        ]
        payload = {
            "targetLanguage": language,
            "sceneTitle": title,
            # Original model summary may contradict an owner's correction. Only
            # confirmed labels/facts go to translation after review.
            "sceneSummary": "Reviewed photo objects: " + ", ".join(row.label for row in objects),
            "objects": [{"key": str(row.id), "source": row.label} for row in objects],
            "attributes": [
                {"key": f"{row.key}:color", "source": row.color}
                for row in confirmed.objects
                if row.color
            ],
            "relationships": [{"key": str(row.id), "source": row.relation} for row in relations],
        }
        try:
            # The owner's language pack guides the translation when one is ready.
            context = _game_context(profile)
            translated = SceneTranslationResult.model_validate(
                self.translator.translate(
                    payload,
                    cache_scope=CacheScope(f"user:{owner_id}:room:{room_id}"),
                    language_context=context,
                )
            )
            if context is None:
                translated = normalize_object_articles(translated, payload["targetLanguage"])
            validate_translation_terms(payload, translated, context)
            if any(
                len(rows) != len({row.key for row in rows})
                for rows in (translated.objects, translated.attributes, translated.relationships)
            ):
                raise ValueError("Translation repeated a reviewed fact.")
        except Exception as error:
            raise RoomPhotoError(
                "room_photo_translation_failed",
                "The reviewed words could not be translated. Please try confirming them again.",
            ) from error
        try:
            return build_room_pack(photo_id, title, objects, relations, translated, language)
        except RoomClueError as error:
            raise RoomPhotoError("room_photo_no_clues", str(error)) from error
