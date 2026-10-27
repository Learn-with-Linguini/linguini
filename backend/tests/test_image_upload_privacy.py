"""Accepted originals must not retain camera, location, or descriptive metadata."""

from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PIL import Image, PngImagePlugin
from PIL.TiffImagePlugin import IFDRational

from app.schemas.media import MAX_IMAGE_BYTES, ConfirmMediaUploadRequest
from app.schemas.users import User
from app.services.image_storage import InvalidImageUpload
from app.services.image_uploads import sanitize_image_upload
from app.services.media_assets import MediaAssetService
from app.services.media_urls import MediaUrlError


def encoded(format, *, metadata=False, alpha=False):
    image = Image.new("RGBA" if alpha else "RGB", (12, 8), (255, 0, 0, 64) if alpha else "red")
    output = BytesIO()
    options = {"lossless": True} if format == "WEBP" else {}
    if metadata:
        exif = Image.Exif()
        exif[274] = 6
        exif[34853] = {1: "N", 2: (IFDRational(1), IFDRational(2), IFDRational(3))}
        exif[37510] = b"private camera comment"
        options["exif"] = exif
    image.save(output, format=format, **options)
    return output.getvalue()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_originals_remove_gps_and_camera_metadata_and_bake_orientation(format):
    original = encoded(format, metadata=True)
    clean, mime, width, height = sanitize_image_upload(original)
    assert (mime, width, height) == (f"image/{format.lower()}", 8, 12)
    assert b"private camera comment" not in clean
    with Image.open(BytesIO(clean)) as image:
        assert image.size == (8, 12)
        assert not image.getexif()
        assert "exif" not in image.info
    # Retrying an uncommitted confirmation must not encode a JPEG a second time.
    assert sanitize_image_upload(clean)[0] == clean


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_metadata_free_originals_remain_byte_identical(format):
    original = encoded(format)
    assert sanitize_image_upload(original)[0] == original


@pytest.mark.parametrize("format", ["PNG", "WEBP"])
def test_metadata_removal_preserves_transparent_pixels(format):
    clean, _, _, _ = sanitize_image_upload(encoded(format, metadata=True, alpha=True))
    with Image.open(BytesIO(clean)) as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 64


def test_png_text_and_xmp_are_removed():
    output = BytesIO()
    text = PngImagePlugin.PngInfo()
    text.add_text("Comment", "private home address")
    text.add_itxt("XML:com.adobe.xmp", "private GPS location")
    Image.new("RGB", (12, 8), "red").save(output, format="PNG", pnginfo=text)
    clean, _, _, _ = sanitize_image_upload(output.getvalue())
    assert b"private" not in clean
    with Image.open(BytesIO(clean)) as image:
        assert not image.info


def test_metadata_removal_preserves_16_bit_png_values():
    output = BytesIO()
    text = PngImagePlugin.PngInfo()
    text.add_text("Comment", "private address")
    Image.new("I;16", (12, 8), 60000).save(output, format="PNG", pnginfo=text)
    clean, mime, width, height = sanitize_image_upload(output.getvalue())
    assert (mime, width, height) == ("image/png", 12, 8)
    with Image.open(BytesIO(clean)) as image:
        assert image.getpixel((0, 0)) == 60000
        assert "Comment" not in image.info


def test_png_transparent_color_is_preserved_when_text_is_removed():
    output = BytesIO()
    text = PngImagePlugin.PngInfo()
    text.add_text("Comment", "private address")
    Image.new("RGB", (12, 8), "red").save(
        output, format="PNG", transparency=(255, 0, 0), pnginfo=text,
    )
    clean, _, _, _ = sanitize_image_upload(output.getvalue())
    with Image.open(BytesIO(clean)) as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0
        assert "Comment" not in image.info


def test_jpeg_comment_not_exposed_as_exif_is_removed():
    original = encoded("JPEG")
    comment = b"private GPS location"
    original = original[:2] + b"\xff\xfe" + (len(comment) + 2).to_bytes(2) + comment + original[2:]
    clean, _, _, _ = sanitize_image_upload(original)
    assert comment not in clean


def test_metadata_bearing_animation_uses_only_the_first_displayed_frame():
    output = BytesIO()
    Image.new("RGBA", (12, 8), "red").save(
        output, format="WEBP", save_all=True,
        append_images=[Image.new("RGBA", (12, 8), "blue")],
        xmp=b"private location", lossless=True, duration=100,
    )
    clean, _, width, height = sanitize_image_upload(output.getvalue())
    assert (width, height) == (12, 8)
    with Image.open(BytesIO(clean)) as image:
        assert image.n_frames == 1
        assert image.convert("RGB").getpixel((0, 0)) == (255, 0, 0)
        assert "xmp" not in image.info


@pytest.mark.parametrize("data", [b"", b"not an image", b"x" * (MAX_IMAGE_BYTES + 1)])
def test_invalid_or_oversized_uploads_still_fail(data):
    with pytest.raises(InvalidImageUpload):
        sanitize_image_upload(data)


@pytest.mark.parametrize("pixel_limit", [10, 60])
def test_excessive_pixel_counts_are_rejected(monkeypatch, pixel_limit):
    original = encoded("PNG", metadata=True)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", pixel_limit)
    with pytest.raises(InvalidImageUpload):
        sanitize_image_upload(original)


def test_malformed_exif_returns_an_invalid_upload_error():
    output = BytesIO()
    Image.new("RGB", (12, 8)).save(output, format="PNG", exif=b"Exif\0\0private")
    with pytest.raises(InvalidImageUpload):
        sanitize_image_upload(output.getvalue())


@pytest.fixture
def confirmation():
    user = User(display_name="Upload test", auth_provider_id=f"test-{uuid4()}")
    users = MagicMock()
    users.get_current_user.return_value = user
    repository = MagicMock()
    repository.get_by_ids.return_value = {}
    repository.create.side_effect = lambda asset: asset
    storage = MagicMock()
    storage.read_url.return_value = "https://example.com/read"
    asset_id = uuid4()
    request = ConfirmMediaUploadRequest(
        asset_id=asset_id, storage_key=f"users/{user.id}/images/{asset_id}.jpg", source="camera",
    )
    return MediaAssetService(repository, users, storage), repository, storage, request


def test_confirmation_stores_clean_original_before_creating_or_signing_asset(confirmation):
    service, repository, storage, request = confirmation
    original = encoded("JPEG", metadata=True)
    storage.download.return_value = original
    calls = []

    def put(key, data, mime):
        calls.append("put")
        assert key == request.storage_key and mime == "image/jpeg"
        assert data != original and b"private camera comment" not in data

    def create(asset):
        calls.append("create")
        assert calls == ["put", "create"]
        return asset

    storage.put.side_effect = put
    repository.create.side_effect = create
    response = service.confirm_upload(request)
    assert (response.width, response.height) == (8, 12)
    assert calls == ["put", "create"]
    storage.read_url.assert_called_once_with(request.storage_key)


def test_confirmation_cannot_publish_asset_when_sanitized_storage_write_fails(confirmation):
    service, repository, storage, request = confirmation
    storage.download.return_value = encoded("JPEG", metadata=True)
    storage.put.side_effect = MediaUrlError("Storage unavailable.")
    with pytest.raises(MediaUrlError):
        service.confirm_upload(request)
    repository.create.assert_not_called()
    storage.read_url.assert_not_called()


def test_clean_upload_confirmation_does_not_rewrite_storage(confirmation):
    service, repository, storage, request = confirmation
    storage.download.return_value = encoded("JPEG")
    service.confirm_upload(request)
    storage.put.assert_not_called()
    repository.create.assert_called_once()
