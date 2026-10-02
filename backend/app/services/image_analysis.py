"""Replace this extractor with a vision provider when real detection is ready."""

from uuid import UUID, uuid5

from app.schemas.media import MediaAsset, SceneObject


class PlaceholderImageExtractor:
    def extract(self, asset: MediaAsset, session_id: UUID) -> list[SceneObject]:
        # Deliberately fixed sample data, not observations about the uploaded image.
        return [
            SceneObject(
                id=uuid5(session_id, f"placeholder-v1:{label}"),
                session_id=session_id,
                label=label,
                bounding_box={"x": x, "y": y, "width": 0.2, "height": 0.25},
                confidence_score=None,
                source_object_key=f"placeholder-v1:{label}",
            )
            for label, x, y in [("chair", 0.1, 0.5), ("table", 0.4, 0.4), ("plant", 0.7, 0.15)]
        ]
