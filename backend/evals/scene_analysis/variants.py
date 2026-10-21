"""Deterministic image degradations for the scene-analysis eval dataset.

Real users photograph scenes with a phone, in a hurry, indoors. The dataset has
to contain those photos, not just clean stock imagery, or an eval will happily
report that every model is excellent and tell us nothing about which one to
ship.

Rather than hunt for naturally-bad photos, we derive them: every variant here is
a reproducible transform of a base image, so the ground truth for a variant can
be reasoned about directly from the ground truth of its parent ("the globe is
still visible under mild blur; nothing is visible at all in the unusable
variant"). Everything is seeded, so regenerating the dataset produces
byte-comparable images and eval numbers stay comparable across runs.

Run ``python -m evals.scene_analysis.variants`` from ``backend/`` to rebuild
``images/``.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

SEED = 3216
MAX_EDGE = 1280
"""Long edge of a generated image. Phone photos are larger, but every provider
downsamples before tokenising and the smaller files keep the repo light."""

Rect = tuple[float, float, float, float]
"""Normalized crop rect: (x0, y0, x1, y1)."""


def _fit(image: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    scale = min(1.0, max_edge / max(image.size))
    if scale == 1.0:
        return image
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.LANCZOS)


def _crop(image: Image.Image, rect: Rect) -> Image.Image:
    x0, y0, x1, y1 = rect
    box = (
        round(x0 * image.width),
        round(y0 * image.height),
        round(x1 * image.width),
        round(y1 * image.height),
    )
    return image.crop(box)


def _motion_blur(image: Image.Image, distance: int = 18) -> Image.Image:
    """Approximate a horizontal camera smear by averaging shifted copies."""
    base = image.convert("RGB")
    accumulator = base.copy()
    for offset in range(1, distance):
        shifted = base.transform(
            base.size,
            Image.AFFINE,
            (1, 0, -offset, 0, 1, 0),
            resample=Image.BILINEAR,
        )
        accumulator = Image.blend(accumulator, shifted, 1 / (offset + 1))
    return accumulator


def _sensor_noise(image: Image.Image, strength: int = 26) -> Image.Image:
    """Luminance noise of the kind a phone produces in a dim shop."""
    rng = random.Random(SEED)
    base = image.convert("RGB")
    pixels = bytearray(base.tobytes())
    for index in range(0, len(pixels), 3):
        jitter = rng.randint(-strength, strength)
        for channel in range(3):
            value = pixels[index + channel] + jitter
            pixels[index + channel] = 0 if value < 0 else 255 if value > 255 else value
    return Image.frombytes("RGB", base.size, bytes(pixels))


def _low_resolution(image: Image.Image, width: int = 200) -> Image.Image:
    """Downscale hard, then back up: the look of a heavily compressed upload."""
    height = round(image.height * width / image.width)
    small = image.resize((width, height), Image.BILINEAR)
    return small.resize(image.size, Image.BILINEAR)


@dataclass(frozen=True)
class Variant:
    name: str
    transform: Callable[[Image.Image], Image.Image]
    quality: int = 88
    note: str = ""


def _brightness(factor: float) -> Callable[[Image.Image], Image.Image]:
    return lambda image: ImageEnhance.Brightness(image).enhance(factor)


def _blur(radius: float) -> Callable[[Image.Image], Image.Image]:
    return lambda image: image.filter(ImageFilter.GaussianBlur(radius))


def _cropped(rect: Rect) -> Callable[[Image.Image], Image.Image]:
    return lambda image: _crop(image, rect)


def _tilted(degrees: float) -> Callable[[Image.Image], Image.Image]:
    return lambda image: image.rotate(
        degrees, resample=Image.BICUBIC, expand=True, fillcolor=(18, 18, 20)
    )


def _unusable(image: Image.Image) -> Image.Image:
    """Past the point of honest interpretation: the empty-array fallback case."""
    dark = ImageEnhance.Brightness(image).enhance(0.07)
    return dark.filter(ImageFilter.GaussianBlur(24))


def _washed_out(image: Image.Image) -> Image.Image:
    bright = ImageEnhance.Brightness(image).enhance(1.95)
    return ImageEnhance.Contrast(bright).enhance(0.55)


CLASSROOM_VARIANTS: tuple[Variant, ...] = (
    Variant("clean", lambda image: image, note="baseline"),
    Variant("blur-mild", _blur(3.2), note="handheld softness; objects still readable"),
    Variant("low-light", _brightness(0.24), note="lights off, blinds drawn"),
    Variant(
        "crop-desk",
        _cropped((0.05, 0.32, 0.42, 0.70)),
        note="tight crop onto the teacher's desk; context removed",
    ),
    Variant("tilted", _tilted(13), note="phone held at an angle"),
    Variant("noise", _sensor_noise, note="high-ISO grain"),
    Variant("unusable", _unusable, note="expects an empty objects array"),
)

GROCERY_VARIANTS: tuple[Variant, ...] = (
    Variant("clean", lambda image: image, note="baseline; cluttered and dim"),
    Variant("blur-heavy", _blur(9.5), note="badly out of focus"),
    Variant(
        "crop-produce",
        _cropped((0.04, 0.48, 0.46, 0.97)),
        note="densely packed produce; adjacent boxes will overlap",
    ),
    Variant("low-res", _low_resolution, note="heavily downscaled upload"),
    Variant("jpeg", lambda image: image, quality=7, note="severe compression blocking"),
    Variant("overexposed", _washed_out, note="blown-out highlights"),
    Variant("motion", _motion_blur, note="camera moved during capture"),
)

SOURCES: tuple[tuple[str, str, tuple[Variant, ...]], ...] = (
    ("classroom", "../../../frontend/public/scenes/classroom.jpg", CLASSROOM_VARIANTS),
    ("grocery", "../../../frontend/public/scenes/grocery-store.jpg", GROCERY_VARIANTS),
)


def build(output_dir: Path, root: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stem, relative_source, variants in SOURCES:
        with Image.open((root / relative_source).resolve()) as handle:
            base = _fit(handle.convert("RGB"))
        for variant in variants:
            image = _fit(variant.transform(base.copy()))
            destination = output_dir / f"{stem}-{variant.name}.jpg"
            image.save(destination, "JPEG", quality=variant.quality, optimize=True)
            written.append(destination)
    return written


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    paths = build(here / "images", here)
    for path in paths:
        print(f"{path.name:32} {path.stat().st_size / 1024:7.1f} KiB")
