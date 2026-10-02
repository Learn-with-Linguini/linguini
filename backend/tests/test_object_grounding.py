from contextlib import nullcontext
from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

from PIL import Image

from app.ai.features.object_grounding import GroundedBox
from app.ai.features.object_grounding.mapping import apply_object_grounding
from app.ai.features.object_grounding.service import GroundingDinoObjectGrounder, _canonical_label
from app.schemas.media import AnchorPoint, BoundingBox, SceneObject
from app.services.scene_analysis import SceneAnalysisResult
from app.services.vision_model import VisionImage


class FakeGrounder:
    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = []

    def ground(self, image, labels):
        self.calls.append((image, labels))
        return self.boxes


def _result() -> SceneAnalysisResult:
    return SceneAnalysisResult(
        title="Kitchen",
        objects=[
            SceneObject(
                session_id=uuid4(),
                label="chair",
                bounding_box=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2),
                anchor_point=AnchorPoint(x=0.15, y=0.15),
            ),
            SceneObject(
                session_id=uuid4(),
                label="table",
                bounding_box=BoundingBox(x=0.5, y=0.1, width=0.2, height=0.2),
            ),
        ],
    )


def test_detector_prompt_labels_match_the_scene_analysis_labels() -> None:
    assert _canonical_label("a pizza") == "pizza"
    assert _canonical_label("an apple.") == "apple"
    assert _canonical_label("the basket") == "basket"


def _detector(results, *, max_labels=12, max_image_side=1024):
    detector = GroundingDinoObjectGrounder.__new__(GroundingDinoObjectGrounder)
    detector._torch = MagicMock()
    detector._torch.inference_mode.side_effect = nullcontext
    detector._model = MagicMock()
    detector._processor = MagicMock()
    detector._processor.return_value.to.return_value = (
        detector._processor.return_value
    )
    detector._processor.post_process_grounded_object_detection.return_value = results
    detector._threshold = 0.35
    detector._device = "cpu"
    detector._max_labels = max_labels
    detector._max_image_side = max_image_side
    return detector


def _png(width: int = 100, height: int = 100) -> VisionImage:
    data = BytesIO()
    Image.new("RGB", (width, height)).save(data, format="PNG")
    return VisionImage(data=data.getvalue(), mime_type="image/png")


def test_one_batched_pass_accepts_partial_returned_phrase() -> None:
    box = MagicMock()
    box.tolist.return_value = [10, 20, 40, 60]
    detector = _detector(
        [{"boxes": [box], "scores": [0.8], "text_labels": ["plant"]}]
    )
    boxes = detector.ground(
        _png(),
        ["hanging plant", "lamp", "hanging plant"],
    )
    assert detector._model.call_count == 1
    assert detector._processor.call_count == 1
    assert detector._processor.call_args.kwargs["text"] == "hanging plant. lamp."
    assert list(boxes) == ["hanging plant"]
    assert boxes["hanging plant"].score == 0.8
    assert boxes["hanging plant"].x == 0.1


def test_highest_score_per_label_and_returned_box_assignment() -> None:
    weak, strong = MagicMock(), MagicMock()
    weak.tolist.return_value = [0, 0, 10, 10]
    strong.tolist.return_value = [20, 20, 60, 60]
    detector = _detector(
        [
            {
                "boxes": [weak, strong],
                "scores": [0.5, 0.9],
                "text_labels": ["plant", "plant"],
            }
        ]
    )
    boxes = detector.ground(_png(), ["plant", "the plant", "lamp"])
    # Both original labels that canonicalize to "plant" get the same best box.
    assert set(boxes) == {"plant", "the plant"}
    assert boxes["plant"].score == 0.9
    assert boxes["the plant"] == boxes["plant"]
    # Unmatched detections (below threshold, absent from results) stay absent.
    assert "lamp" not in boxes


def test_label_cap_limits_the_joined_prompt() -> None:
    detector = _detector(
        [{"boxes": [], "scores": [], "text_labels": []}], max_labels=2
    )
    detector.ground(_png(), ["one", "two", "three", "four"])
    assert detector._processor.call_args.kwargs["text"] == "one. two."


def test_oversized_images_are_downscaled_before_the_forward_pass() -> None:
    box = MagicMock()
    box.tolist.return_value = [512, 0, 1024, 1024]
    detector = _detector(
        [{"boxes": [box], "scores": [0.7], "text_labels": ["chair"]}]
    )
    boxes = detector.ground(_png(2048, 1024), ["chair"])
    image = detector._processor.call_args.kwargs["images"]
    assert max(image.size) == 1024
    assert image.size == (1024, 512)
    # Coordinates normalize against the resized dimensions.
    assert boxes["chair"].x == 0.5
    assert boxes["chair"].width == 0.5
    call = detector._processor.post_process_grounded_object_detection.call_args
    assert call.kwargs["target_sizes"] == [(512, 1024)]


def test_grounding_replaces_the_detector_matched_box_and_anchor() -> None:
    grounder = FakeGrounder(
        {"chair": GroundedBox(x=0.3, y=0.4, width=0.2, height=0.1, score=0.9)}
    )

    result = apply_object_grounding(
        _result(), VisionImage(data=b"image", mime_type="image/png"), grounder
    )

    chair, table = result.objects
    assert chair.bounding_box.model_dump(mode="json") == {
        "x": "0.3",
        "y": "0.4",
        "width": "0.2",
        "height": "0.1",
    }
    assert chair.anchor_point.model_dump(mode="json") == {"x": "0.4", "y": "0.45"}
    assert table.bounding_box.model_dump(mode="json") == {
        "x": "0.5",
        "y": "0.1",
        "width": "0.2",
        "height": "0.2",
    }
    assert grounder.calls[0][1] == ["chair", "table"]
