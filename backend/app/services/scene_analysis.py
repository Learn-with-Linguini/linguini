"""Provider seam for scene analysis.

Swapping in a real scene-analysis service means adding another ``SceneAnalyzer``
implementation and changing only the wiring in ``app/api/dependencies.py``.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel

from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.schemas.sessions import Session
from app.services.session_plan import build_objects


class SceneAnalysisResult(BaseModel):
    title: str
    summary: str | None = None
    objects: list[SceneObject]
    relations: list[SceneObjectRelation] = []


class SceneAnalysisError(Exception):
    """Raised when a scene-analysis provider fails."""


class SceneAnalyzer(Protocol):
    def analyze(
        self,
        session: Session,
        asset: MediaAsset,
        profile: Mapping[str, Any],
        scene: Mapping[str, Any] | None,
    ) -> SceneAnalysisResult: ...


class DeterministicSceneAnalyzer:
    """Placeholder analyzer; wraps the existing deterministic plan builder."""

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
        summary = scene["description"] if scene else None
        if not summary and objects:
            labels = ", ".join(obj.label for obj in objects)
            summary = f"Words to practise in this photo: {labels}."
        item_ids = {
            entry["id"]: obj.id
            for entry, obj in zip(scene["content"]["items"], objects, strict=True)
        } if scene else {}
        curated_relations = [
            SceneObjectRelation(
                subject_scene_object_id=item_ids[row["subjectItemId"]],
                relation=row["relation"],
                reference_scene_object_id=item_ids[row["referenceItemId"]],
                source_relation_key="precomputed-v1",
            )
            for row in (scene["content"].get("relations", []) if scene else [])
        ]
        return SceneAnalysisResult(
            title=title, summary=summary, objects=objects,
            relations=curated_relations or self._relations(objects),
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
