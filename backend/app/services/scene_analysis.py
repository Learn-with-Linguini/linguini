"""Provider seam for scene analysis.

Swapping in a real scene-analysis service means adding another ``SceneAnalyzer``
implementation and changing only the wiring in ``app/api/dependencies.py``.
"""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import uuid5

from pydantic import BaseModel

from app.schemas.media import (
    MediaAsset,
    SceneActionSuggestion,
    SceneObject,
    SceneObjectRelation,
    ScenePriceSuggestion,
)
from app.schemas.sessions import Session
from app.services.session_plan import build_objects


class SceneAnalysisResult(BaseModel):
    content_hash: str | None = None
    title: str
    summary: str | None = None
    objects: list[SceneObject]
    relations: list[SceneObjectRelation] = []
    action_suggestions: list[SceneActionSuggestion] = []
    price_suggestions: list[ScenePriceSuggestion] = []


class SceneAnalysisError(Exception):
    """Raised when a scene-analysis provider fails."""


def uploaded_scene_title(result: SceneAnalysisResult) -> str:
    """Replace provider placeholder titles with a useful, observed photo title."""
    generic = {"user uploaded photo", "uploaded photo", "your uploaded photo", "untitled"}
    if result.title.strip().lower() not in generic:
        return result.title
    labels = list(
        dict.fromkeys(item.label.strip() for item in result.objects if item.label.strip())
    )[:3]
    if not labels:
        return "Your photo"
    if len(labels) == 1:
        return f"A photo of a {labels[0]}"
    if len(labels) == 2:
        return f"A photo of {labels[0]} and {labels[1]}"
    return f"A photo of {labels[0]}, {labels[1]} and {labels[2]}"


def scene_inventory(result: SceneAnalysisResult) -> dict[str, Any]:
    """Asset-scoped, provider-neutral facts without session-specific identifiers."""
    source_keys = {item.id: item.source_object_key for item in result.objects}
    if any(key is None for key in source_keys.values()):
        raise SceneAnalysisError("Analysed objects require source keys for reuse.")
    return {
        "title": result.title,
        "summary": result.summary,
        "objects": [
            item.model_dump(
                mode="json",
                by_alias=True,
                exclude={"id", "session_id", "vocabulary_item_id"},
            )
            for item in result.objects
        ],
        "relations": [
            {
                "relationKey": item.source_relation_key,
                "subjectObjectKey": source_keys[item.subject_scene_object_id],
                "relation": item.relation,
                "referenceObjectKey": source_keys[item.reference_scene_object_id],
            }
            for item in result.relations
        ],
        "actionSuggestions": [
            {
                "actionKey": item.action_key,
                "action": item.action,
                "relatedObjectKeys": [source_keys[key] for key in item.scene_object_ids],
                "confidenceScore": str(item.confidence_score),
            }
            for item in result.action_suggestions
        ],
        "priceSuggestions": [
            {
                "priceKey": item.price_key,
                "objectKey": source_keys[item.scene_object_id],
                "displayedPrice": item.displayed_price,
                "confidenceScore": str(item.confidence_score),
            }
            for item in result.price_suggestions
        ],
    }


def scene_result_from_inventory(
    session: Session, inventory: Mapping[str, Any]
) -> SceneAnalysisResult:
    """Hydrate one reusable image inventory with stable IDs for this session."""
    objects = []
    object_ids = {}
    for stored in inventory.get("objects", []):
        source_key = stored["sourceObjectKey"]
        object_id = uuid5(session.id, f"scene-object:{source_key}")
        object_ids[source_key] = object_id
        objects.append(
            SceneObject.model_validate(
                {
                    **stored,
                    "id": object_id,
                    "sessionId": session.id,
                    "vocabularyItemId": None,
                }
            )
        )
    relations = [
        SceneObjectRelation(
            id=uuid5(session.id, f"scene-relation:{stored['relationKey']}"),
            subject_scene_object_id=object_ids[stored["subjectObjectKey"]],
            relation=stored["relation"],
            reference_scene_object_id=object_ids[stored["referenceObjectKey"]],
            source_relation_key=stored["relationKey"],
        )
        for stored in inventory.get("relations", [])
        if stored.get("subjectObjectKey") in object_ids
        and stored.get("referenceObjectKey") in object_ids
    ]
    actions = [
        SceneActionSuggestion(
            action_key=stored["actionKey"],
            action=stored["action"],
            scene_object_ids=[object_ids[key] for key in stored["relatedObjectKeys"]],
            confidence_score=stored["confidenceScore"],
        )
        for stored in inventory.get("actionSuggestions", [])
        if all(key in object_ids for key in stored.get("relatedObjectKeys", []))
    ]
    prices = [
        ScenePriceSuggestion(
            price_key=stored["priceKey"],
            scene_object_id=object_ids[stored["objectKey"]],
            displayed_price=stored["displayedPrice"],
            confidence_score=stored["confidenceScore"],
        )
        for stored in inventory.get("priceSuggestions", [])
        if stored.get("objectKey") in object_ids
    ]
    return SceneAnalysisResult(
        title=inventory["title"],
        summary=inventory.get("summary"),
        objects=objects,
        relations=relations,
        action_suggestions=actions,
        price_suggestions=prices,
    )


class SceneAnalysisUnavailableError(SceneAnalysisError):
    code = "analysisUnavailable"


class UnavailableSceneAnalyzer:
    """Fails uploaded-photo analysis clearly when no provider is configured."""

    def analyze(
        self,
        session: Session,
        asset: MediaAsset,
        profile: Mapping[str, Any],
        scene: Mapping[str, Any] | None,
    ) -> SceneAnalysisResult:
        raise SceneAnalysisUnavailableError(
            "No scene-analysis provider is configured for uploaded photos."
        )


class SceneAnalyzer(Protocol):
    def analyze(
        self,
        session: Session,
        asset: MediaAsset,
        profile: Mapping[str, Any],
        scene: Mapping[str, Any] | None,
    ) -> SceneAnalysisResult: ...


def scene_summary(scene: Mapping[str, Any] | None, objects: list[SceneObject]) -> str | None:
    summary = scene["description"] if scene else None
    if not summary and objects:
        labels = ", ".join(obj.label for obj in objects)
        summary = f"Words to practise in this photo: {labels}."
    return summary


def curated_relations(
    scene: Mapping[str, Any], objects: list[SceneObject]
) -> list[SceneObjectRelation]:
    """The curated relations between ``objects``, built in item order from ``scene``."""
    item_ids = {
        entry["id"]: obj.id
        for entry, obj in zip(scene["content"]["items"], objects, strict=True)
    }
    return [
        SceneObjectRelation(
            subject_scene_object_id=item_ids[row["subjectItemId"]],
            relation=row["relation"],
            reference_scene_object_id=item_ids[row["referenceItemId"]],
            source_relation_key="precomputed-v1",
        )
        for row in scene["content"].get("relations", [])
    ]


class DeterministicSceneAnalyzer:
    """Analyzes curated scenes; tests also use it for uploaded-photo fixtures."""

    def __init__(self, engine):
        self.engine = engine

    def analyze(
        self,
        session: Session,
        asset: MediaAsset,
        profile: Mapping[str, Any],
        scene: Mapping[str, Any] | None,
    ) -> SceneAnalysisResult:
        # Vocabulary bootstrap rows commit in their own short transaction; the
        # caller's session workflow stays outside it.
        with self.engine.begin() as connection:
            objects, _, _ = build_objects(connection, session, asset, profile, scene)
        title = scene["title"] if scene else "Your uploaded photo"
        curated = curated_relations(scene, objects) if scene else []
        return SceneAnalysisResult(
            title=title, summary=scene_summary(scene, objects), objects=objects,
            relations=curated or self._relations(objects),
        )

    @staticmethod
    def _relations(objects: list[SceneObject]) -> list[SceneObjectRelation]:
        boxed = sorted(
            (obj for obj in objects if obj.bounding_box is not None),
            key=lambda obj: float(obj.bounding_box.x),
        )
        relations = []
        for index, (left, right) in enumerate(zip(boxed, boxed[1:], strict=False)):
            difference = float(left.bounding_box.y) - float(right.bounding_box.y)
            relation = (
                "beside" if abs(difference) <= 0.2 else ("above" if difference < 0 else "below")
            )
            relations.append(
                SceneObjectRelation(
                    subject_scene_object_id=left.id,
                    relation=relation,
                    reference_scene_object_id=right.id,
                    source_relation_key=f"deterministic-v1:{index}",
                )
            )
        return relations
