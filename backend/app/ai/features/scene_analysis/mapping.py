"""Map validated scene-analysis model output onto domain objects."""

from __future__ import annotations

from uuid import uuid5

from app.ai.features.scene_analysis.schemas import (
    ModelAnchorPoint,
    ModelBoundingBox,
    SceneAnalysisModelResult,
)
from app.schemas.media import SceneObject, SceneObjectRelation
from app.schemas.sessions import Session
from app.services.scene_analysis import SceneAnalysisError, SceneAnalysisResult

MIN_OBJECT_CONFIDENCE = 0.7
MIN_RELATION_CONFIDENCE = 0.7
_ANCHOR_TOLERANCE = 1e-9


def _anchor_for(
    anchor: ModelAnchorPoint | None, box: ModelBoundingBox
) -> dict[str, float] | None:
    """Pass through an in-box anchor; fall back to the box centre otherwise."""
    if anchor is None:
        return None
    inside = (
        box.x - _ANCHOR_TOLERANCE <= anchor.x <= box.x + box.width + _ANCHOR_TOLERANCE
        and box.y - _ANCHOR_TOLERANCE
        <= anchor.y
        <= box.y + box.height + _ANCHOR_TOLERANCE
    )
    if inside:
        return {"x": anchor.x, "y": anchor.y}
    return {"x": box.x + box.width / 2, "y": box.y + box.height / 2}


def model_result_to_domain(
    session: Session, result: SceneAnalysisModelResult
) -> SceneAnalysisResult:
    """Apply provider-neutral confidence filtering and stable domain IDs."""
    retained = [
        item for item in result.objects if item.confidence >= MIN_OBJECT_CONFIDENCE
    ]
    if not retained:
        raise SceneAnalysisError("No reliable learning objects were found.")

    object_ids = {
        item.key: uuid5(session.id, f"scene-object:{item.key}") for item in retained
    }
    objects = [
        SceneObject(
            id=object_ids[item.key],
            session_id=session.id,
            label=item.label,
            bounding_box=item.bounding_box.model_dump(),
            anchor_point=_anchor_for(item.anchor_point, item.bounding_box),
            attributes={
                attribute.type.value: attribute.value
                for attribute in item.attributes
            },
            confidence_score=item.confidence,
            source_object_key=item.key,
        )
        for item in retained
    ]
    relations = [
        SceneObjectRelation(
            id=uuid5(session.id, f"scene-relation:{item.key}"),
            subject_scene_object_id=object_ids[item.source_object_key],
            relation=item.relation_type.value,
            reference_scene_object_id=object_ids[item.target_object_key],
            source_relation_key=item.key,
        )
        for item in result.relations
        if item.confidence >= MIN_RELATION_CONFIDENCE
        and item.source_object_key in object_ids
        and item.target_object_key in object_ids
    ]
    return SceneAnalysisResult(
        title=result.title,
        summary=result.summary,
        objects=objects,
        relations=relations,
    )
