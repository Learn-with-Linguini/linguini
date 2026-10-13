"""Fail-closed uploaded-room preparation; owns no sessions or database writes."""

import copy
import hashlib
from typing import Annotated
from uuid import UUID

from pydantic import Field, ValidationError, field_validator, model_validator

from app.ai.cache import CacheScope
from app.ai.contracts import VisionImage
from app.ai.features.moderation import ImageModerationError, ImageModerationResult
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


class _PreparedStorage:
    """Analyze precisely the bytes that passed moderation, without a second download."""

    def __init__(self, storage_key: str, data: bytes):
        self.key, self.data = storage_key, data

    def download(self, storage_key: str) -> bytes:
        if storage_key != self.key:
            raise RoomPhotoError("room_photo_analysis_failed", "The photo changed during analysis.")
        return self.data


class _PassedModerator:
    """Per-call moderation memo; never changes the application-scoped analyzer."""

    def __init__(self, image: VisionImage, verdict: ImageModerationResult):
        self.digest = hashlib.sha256(image.data).digest()
        self.mime_type = image.mime_type
        self.verdict = verdict

    def moderate(self, image: VisionImage) -> ImageModerationResult:
        if self.mime_type != image.mime_type or self.digest != hashlib.sha256(image.data).digest():
            raise RoomPhotoError("room_photo_analysis_failed", "The photo changed during analysis.")
        return self.verdict


class RoomPhotoPreparer:
    """Injected runtime analyzer/translator, with explicit strict sharing moderation.

    Room services own authorization, leases, bounded job retries and revisions.
    These synchronous helpers must run outside their database transactions. A
    successful analysis permits sharing; translation waits for owner confirmation.
    """

    def __init__(self, analyzer, translator, *, storage, image_moderator):
        self.analyzer, self.translator = analyzer, translator
        self.storage, self.image_moderator = storage, image_moderator

    @staticmethod
    def _language(profile: dict) -> str:
        language = str(profile.get("target_language_code", "")).lower()
        source = str(profile.get("source_language_code", "en")).lower()
        if language not in {"es", "fr"} or source != "en":
            raise RoomPhotoError(
                "room_photo_unavailable",
                "Photo rooms currently support English to Spanish or French.",
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
        if self.analyzer is None or self.image_moderator is None or self.storage is None:
            raise RoomPhotoError(
                "room_photo_unavailable",
                "Photo analysis and image moderation must be configured "
                "before a room can share uploads.",
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
        try:
            verdict = self.image_moderator.moderate(image)
            if not isinstance(verdict, ImageModerationResult) or not isinstance(
                verdict.flagged, bool
            ):
                raise ImageModerationError("Moderation returned no usable verdict.")
        except Exception as error:
            raise RoomPhotoError(
                "room_photo_moderation_unavailable",
                "Image checks are unavailable. This photo stays private; please try again.",
            ) from error
        if verdict.flagged:
            raise RoomPhotoError(
                "room_photo_unsafe",
                "This photo could not be shared. Choose a different photo.",
                retryable=False,
            )

        # Shallow-copy only this concrete analyzer, sharing its immutable provider
        # client and grounder while replacing per-call image/moderation seams.
        # Its usual fail-open moderation behavior remains untouched for solo use.
        analyzer = self.analyzer
        if isinstance(analyzer, UploadedSceneAnalyzer):
            analyzer = copy.copy(analyzer)
            analyzer._storage = _PreparedStorage(asset.storage_key, image.data)
            analyzer._image_moderator = _PassedModerator(image, verdict)
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
            if not result.objects or len(result.objects) > 6:
                raise ValueError("Analysis must return up to six observed objects.")
            if len({obj.id for obj in result.objects}) != len(result.objects):
                raise ValueError("Analysis repeated an object.")
            selected = {obj.id for obj in result.objects}
            rows = []
            for obj in result.objects:
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
                if (
                    not {relation.subject_scene_object_id, relation.reference_scene_object_id}
                    <= selected
                ):
                    raise ValueError("Analysis returned a relationship outside the photo.")
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
            "moderationPassed": True,
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
            analysis.get("moderationPassed") is not True
            or analysis.get("photoId") != str(photo_id)
            or analysis.get("ownerId") != str(owner_id)
        ):
            raise RoomPhotoError(
                "room_photo_review_invalid",
                "Review your own checked photo before preparing the game.",
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
            translated = SceneTranslationResult.model_validate(
                self.translator.translate(
                    payload,
                    cache_scope=CacheScope(f"user:{owner_id}:room:{room_id}"),
                )
            )
            translated = normalize_object_articles(translated)
            validate_translation_terms(payload, translated)
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
