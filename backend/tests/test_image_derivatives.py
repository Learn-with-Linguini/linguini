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
