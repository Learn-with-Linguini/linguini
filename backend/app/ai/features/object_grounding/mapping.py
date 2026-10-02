"""Apply detector boxes to accepted scene objects."""

from __future__ import annotations

import logging

from app.ai.features.object_grounding.service import ObjectGrounder
from app.schemas.media import AnchorPoint, BoundingBox
from app.services.scene_analysis import SceneAnalysisResult
from app.services.vision_model import VisionImage

logger = logging.getLogger("uvicorn.error")


def apply_object_grounding(
    result: SceneAnalysisResult, image: VisionImage, grounder: ObjectGrounder
) -> SceneAnalysisResult:
    """Replace only locations that the detector can match with confidence."""
    boxes = grounder.ground(image, [object.label for object in result.objects])
    logger.info(
        "Grounding DINO applied detector boxes to %s of %s scene objects.",
        sum(object.label in boxes for object in result.objects),
        len(result.objects),
    )
    objects = []
    for index, object in enumerate(result.objects, start=1):
        box = boxes.get(object.label)
        if box is None:
            logger.warning(
                "Grounding DINO marker %s: no matching detection; using vision-model location.",
                index,
            )
            objects.append(object)
            continue
        logger.info(
            "Grounding DINO marker %s: detector confidence=%.3f center=(%.3f, %.3f)",
            index, box.score, box.x + box.width / 2, box.y + box.height / 2,
        )
        bounding_box = BoundingBox(
            x=box.x, y=box.y, width=box.width, height=box.height
        )
        objects.append(
            object.model_copy(
                update={
                    "bounding_box": bounding_box,
                    "anchor_point": AnchorPoint(
                        x=box.x + box.width / 2, y=box.y + box.height / 2
                    ),
                }
            )
        )
    return result.model_copy(update={"objects": objects})
