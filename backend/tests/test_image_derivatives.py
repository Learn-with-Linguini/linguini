from io import BytesIO

from PIL import Image

from app.services.image_derivatives import ImageDerivatives


def oriented_jpeg() -> bytes:
    image = Image.new("RGB", (40, 20), "blue")
    exif = Image.Exif()
    exif[274] = 6  # Camera pixels are landscape; display is 90° clockwise.
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_derivative_bakes_phone_orientation_into_pixels():
    derivative = ImageDerivatives._resize(oriented_jpeg(), 640)

    with Image.open(BytesIO(derivative)) as image:
        assert image.format == "WEBP"
        assert image.size == (20, 40)


class RecordingStorage:
    configured = True

    def __init__(self):
        self.deleted = []

    def delete_many(self, keys):
        self.deleted.extend(keys)


def test_removing_a_photo_deletes_the_original_every_resized_copy_and_the_cache():
    storage = RecordingStorage()
    derivatives = ImageDerivatives(storage)
    photo, other = "users/u/images/a.jpg", "users/u/images/b.jpg"
    derivatives._remember((photo, 640), b"a")
    derivatives._remember((other, 640), b"b")
    derivatives.remove([photo])
    assert storage.deleted[0] == photo
    assert {f"derived/v2/w{width}/{photo}.webp" for width in (320, 640, 1280)} <= set(
        storage.deleted
    )
    assert {f"derived/w{width}/{photo}" for width in (320, 640, 1280)} <= set(storage.deleted)
    assert len(storage.deleted) == 7
    assert (photo, 640) not in derivatives._cache and (other, 640) in derivatives._cache
