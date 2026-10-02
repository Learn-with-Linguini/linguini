"""Local Grounding DINO adapter for precise object locations.

The vision model supplies useful vocabulary labels. This adapter receives only
those labels and finds their pixels, so the numbered marker does not depend on
the vision model estimating normalized coordinates.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from app.services.vision_model import VisionImage

logger = logging.getLogger(__name__)


class ObjectGroundingError(RuntimeError):
    """The optional detector could not produce usable locations."""


@dataclass(frozen=True)
class GroundedBox:
    """A detector result in normalized image coordinates."""

    x: float
    y: float
    width: float
    height: float
    score: float


class ObjectGrounder(Protocol):
    def ground(
        self, image: VisionImage, labels: Sequence[str]
    ) -> Mapping[str, GroundedBox]: ...


class GroundingDinoObjectGrounder:
    """Zero-shot detector backed by ``IDEA-Research/grounding-dino-base``.

    Imports and model loading are deliberately lazy. Deployments that do not
    opt into grounding do not need PyTorch, Transformers, or model weights.
    """

    def __init__(
        self,
        model_name: str,
        threshold: float,
        *,
        max_labels: int = 12,
        max_image_side: int = 1024,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as error:
            raise ObjectGroundingError(
                "Grounding DINO needs the 'grounding' backend extra. "
                "Install it before setting AI_OBJECT_GROUNDING_PROVIDER=groundingDino."
            ) from error

        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(model_name)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(model_name)
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        self._device = device
        self._model = self._model.to(device)
        self._model.eval()
        self._threshold = threshold
        self._max_labels = max_labels
        self._max_image_side = max_image_side
        logger.info(
            "Grounding DINO loaded: model=%s device=%s", model_name, device
        )

    def ground(
        self, image: VisionImage, labels: Sequence[str]
    ) -> Mapping[str, GroundedBox]:
        if not labels:
            return {}
        try:
            from PIL import Image, ImageOps

            canonical_to_originals: dict[str, list[str]] = {}
            for label in dict.fromkeys(labels):
                canonical_to_originals.setdefault(
                    _canonical_label(label), []
                ).append(label)
            queried = list(canonical_to_originals)[: self._max_labels]
            if len(canonical_to_originals) > self._max_labels:
                logger.warning(
                    "Grounding DINO label cap: %s of %s labels queried.",
                    self._max_labels,
                    len(canonical_to_originals),
                )
            prompt = " ".join(f"{name}." for name in queried)

            source = ImageOps.exif_transpose(
                Image.open(BytesIO(image.data))
            ).convert("RGB")
            if max(source.size) > self._max_image_side:
                source.thumbnail(
                    (self._max_image_side, self._max_image_side),
                    Image.Resampling.LANCZOS,
                )
            width, height = source.size

            inputs = self._processor(
                images=source, text=prompt, return_tensors="pt"
            ).to(self._device)
            start = time.monotonic()
            with self._torch.inference_mode():
                outputs = self._model(**inputs)
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "Grounding DINO forward pass: labels=%s queried=%s duration_ms=%s image=%sx%s",
                len(labels),
                len(queried),
                duration_ms,
                width,
                height,
            )
            results = self._processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                threshold=self._threshold,
                text_threshold=self._threshold,
                target_sizes=[(height, width)],
            )[0]

            best: dict[str, GroundedBox] = {}
            text_labels = results.get("text_labels") or []
            for index, (box, score) in enumerate(
                zip(results["boxes"], results["scores"], strict=False)
            ):
                text_label = text_labels[index] if index < len(text_labels) else ""
                matched = _match_query(text_label, queried)
                if matched is None:
                    if not text_labels and len(queried) == 1:
                        matched = queried[0]
                    else:
                        continue
                left, top, right, bottom = (float(value) for value in box.tolist())
                normalized = _normalize_box(
                    left, top, right, bottom, width, height, float(score)
                )
                if normalized is None:
                    continue
                for original in canonical_to_originals[matched]:
                    if original not in best or normalized.score > best[original].score:
                        best[original] = normalized
        except Exception as error:
            raise ObjectGroundingError("Grounding DINO could not process this image") from error
        return best


def _canonical_label(label: str) -> str:
    """Match Grounding DINO's prompt phrase (for example, ``a pizza``)."""
    normalized = " ".join(label.casefold().strip().rstrip(".").split())
    for article in ("a ", "an ", "the "):
        if normalized.startswith(article):
            return normalized.removeprefix(article)
    return normalized


def _match_query(text_label: str, queried: Sequence[str]) -> str | None:
    """Map a returned phrase back to one queried canonical label.

    Grounding DINO may drop words or merge phrases in its ``text_labels``, so
    an exact match is preferred and token-set containment is the fallback.
    """
    canonical = _canonical_label(text_label)
    if canonical in queried:
        return canonical
    phrase_tokens = set(canonical.split())
    if not phrase_tokens:
        return None
    candidates = [
        name
        for name in queried
        if phrase_tokens <= set(name.split()) or set(name.split()) <= phrase_tokens
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda name: (len(phrase_tokens & set(name.split())), len(name)),
    )


def _normalize_box(
    left: float, top: float, right: float, bottom: float, width: int, height: int, score: float
) -> GroundedBox | None:
    left, right = sorted((max(0.0, left), min(float(width), right)))
    top, bottom = sorted((max(0.0, top), min(float(height), bottom)))
    if right <= left or bottom <= top:
        return None
    return GroundedBox(
        x=left / width,
        y=top / height,
        width=(right - left) / width,
        height=(bottom - top) / height,
        score=score,
    )
