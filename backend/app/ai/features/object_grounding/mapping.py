"""Apply detector boxes to accepted scene objects."""

from __future__ import annotations

import logging
from decimal import Decimal

from app.ai.contracts import VisionImage
from app.ai.features.object_grounding.service import ObjectGrounder
from app.schemas.media import AnchorPoint, BoundingBox
from app.services.scene_analysis import SceneAnalysisResult

logger = logging.getLogger("uvicorn.error")


def _bounded_box(box_x: float, box_y: float, width: float, height: float) -> BoundingBox:
    """Clamp detector rounding drift to the normalized image boundary."""
    one = Decimal(1)
    x = min(max(Decimal(str(box_x)), Decimal(0)), one)
    y = min(max(Decimal(str(box_y)), Decimal(0)), one)
    right = min(max(x + Decimal(str(width)), x), one)
    bottom = min(max(y + Decimal(str(height)), y), one)
    return BoundingBox(x=x, y=y, width=right - x, height=bottom - y)


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
        bounding_box = _bounded_box(box.x, box.y, box.width, box.height)
        objects.append(
            object.model_copy(
                update={
                    "bounding_box": bounding_box,
                    "anchor_point": AnchorPoint(
                        x=bounding_box.x + bounding_box.width / 2,
                        y=bounding_box.y + bounding_box.height / 2,
                    ),
                }
            )
        )
    return result.model_copy(update={"objects": objects})
