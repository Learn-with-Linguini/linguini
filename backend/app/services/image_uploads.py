"""Validate uploaded images and remove metadata before accepting their originals."""

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas.media import MAX_IMAGE_BYTES
from app.services.image_storage import InvalidImageUpload

IMAGE_MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
RENDERING_INFO = {
    "JPEG": {"jfif", "jfif_version", "jfif_unit", "jfif_density", "adobe", "adobe_transform"},
    "PNG": {"transparency"},
    "WEBP": {"loop", "background", "timestamp", "duration"},
}


def _has_metadata(image: Image.Image, format: str) -> bool:
    if set(image.info) - RENDERING_INFO[format]:
        return True
    if getattr(image, "private_chunks", ()):
        return True
    # Pillow does not put every JPEG application segment (such as IPTC) in info.
    return any(
        not (marker == "APP0" and data.startswith(b"JFIF\0"))
        and not (marker == "APP14" and data.startswith(b"Adobe"))
        for marker, data in getattr(image, "applist", ())
    )


def _clean_frame(frame: Image.Image) -> Image.Image:
    frame = ImageOps.exif_transpose(frame)
    if "transparency" in frame.info:
        frame = frame.convert("RGBA")
    frame.info.clear()
    return frame


def sanitize_image_upload(data: bytes) -> tuple[bytes, str, int, int]:
    """Return accepted bytes, MIME and display dimensions; clean uploads stay unchanged."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise InvalidImageUpload("Image must be between 1 byte and 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                format = image.format
                if format not in IMAGE_MIMES:
                    raise InvalidImageUpload("Use a JPEG, PNG or WebP image.")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                width, height = ImageOps.exif_transpose(image).size
                if not _has_metadata(image, format):
                    return data, IMAGE_MIMES[format], width, height
                # Analysis and derivatives use the first frame. Normalizing only that
                # frame also keeps metadata-bearing animations within the pixel limit.
                frame = _clean_frame(image)
                options = {"quality": 95} if format == "JPEG" else {}
                if format == "WEBP":
                    options = {"lossless": True}
                buffer = BytesIO()
                frame.save(buffer, format=format, **options)
                clean = buffer.getvalue()
                if len(clean) > MAX_IMAGE_BYTES:
                    raise InvalidImageUpload("Image exceeds 10 MB after metadata removal.")
                return clean, IMAGE_MIMES[format], width, height
    except (
        UnidentifiedImageError, OSError, ValueError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageUpload("The uploaded file is not a valid image.") from exc
