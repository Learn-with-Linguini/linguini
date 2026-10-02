"""Derivative image endpoint: cached WebP renditions behind the existing asset authorization."""

from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import delete, insert
from test_postgres_sessions import database as database

from app.api.dependencies import get_media_asset_service
from app.repositories.postgres.media_assets import PostgresMediaAssetRepository, media_assets
from app.repositories.postgres.users import PostgresUserRepository, users
from app.schemas.enums import MediaSource, MediaType
from app.schemas.media import MediaAsset
from app.schemas.users import User
from app.services.image_derivatives import ImageDerivatives
from app.services.image_storage import UploadObjectMissing
from app.services.media_assets import MediaAssetService
from app.services.media_urls import MediaUrlError
from app.services.users import UserService


class FakeStorage:
    def __init__(self, objects=None, remote_objects=None, fail_put=False):
        self.objects = dict(objects or {})
        self.downloads = []
        self.url_downloads = []
        self.remote_objects = dict(remote_objects or {})
        self.puts = []
        self.fail_put = fail_put

    def download(self, key):
        self.downloads.append(key)
        if key not in self.objects:
            raise UploadObjectMissing()
        return self.objects[key]

    def download_url(self, url):
        self.url_downloads.append(url)
        if url not in self.remote_objects:
            raise UploadObjectMissing()
        return self.remote_objects[url]

    def put(self, key, data, content_type):
        self.puts.append(key)
        if self.fail_put:
            raise MediaUrlError("Unable to store derived image.")
        self.objects[key] = data


def jpeg_bytes(width=1600, height=1200):
    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 60, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def install(client, engine, owner, storage):
    service = MediaAssetService(
        PostgresMediaAssetRepository(engine),
        UserService(PostgresUserRepository(engine), owner.id),
        storage,
        ImageDerivatives(storage),
    )
    client.app.dependency_overrides[get_media_asset_service] = lambda: service


def insert_asset(
    engine,
    owner_id=None,
    source=MediaSource.USER_UPLOAD,
    storage_key="users/u/images/a.jpg",
):
    asset = MediaAsset(
        id=uuid4(),
        owner_user_id=owner_id,
        media_type=MediaType.IMAGE,
        source=source,
        storage_key=storage_key,
        mime_type="image/jpeg",
        width=1600,
        height=1200,
    )
    return PostgresMediaAssetRepository(engine).create(asset)


@pytest.fixture
def media_client(database):
    engine, owner, profile, client = database
    try:
        yield engine, owner, client
    finally:
        client.app.dependency_overrides.clear()


def test_image_resizes_to_requested_webp_and_caches_headers(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    storage = FakeStorage({asset.storage_key: jpeg_bytes()})
    install(client, engine, owner, storage)
    response = client.get(f"/api/v1/media/{asset.id}/image?width=320")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert response.headers["etag"].startswith('"') and response.headers["etag"].endswith('"')
    with Image.open(BytesIO(response.content)) as image:
        assert image.format == "WEBP"
        assert image.width <= 320


def test_repeat_request_serves_from_memory_cache(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    storage = FakeStorage({asset.storage_key: jpeg_bytes()})
    install(client, engine, owner, storage)
    assert client.get(f"/api/v1/media/{asset.id}/image?width=640").status_code == 200
    downloads_after_first = list(storage.downloads)
    assert client.get(f"/api/v1/media/{asset.id}/image?width=640").status_code == 200
    assert storage.downloads == downloads_after_first


def test_existing_derivative_skips_the_original_download(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    derived = ImageDerivatives(FakeStorage()).derived_key(asset.storage_key, 640)
    storage = FakeStorage({asset.storage_key: jpeg_bytes(), derived: jpeg_bytes(640, 480)})
    install(client, engine, owner, storage)
    assert client.get(f"/api/v1/media/{asset.id}/image?width=640").status_code == 200
    assert asset.storage_key not in storage.downloads


def test_failing_derivative_writeback_still_serves_the_image(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    storage = FakeStorage({asset.storage_key: jpeg_bytes()}, fail_put=True)
    install(client, engine, owner, storage)
    response = client.get(f"/api/v1/media/{asset.id}/image?width=640")
    assert response.status_code == 200
    assert storage.puts


def test_matching_if_none_match_returns_304(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    storage = FakeStorage({asset.storage_key: jpeg_bytes()})
    install(client, engine, owner, storage)
    first = client.get(f"/api/v1/media/{asset.id}/image?width=320")
    response = client.get(
        f"/api/v1/media/{asset.id}/image?width=320",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert response.status_code == 304
    assert response.headers["etag"] == first.headers["etag"]
    assert not response.content


def test_unlisted_width_is_rejected(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id)
    install(client, engine, owner, FakeStorage({asset.storage_key: jpeg_bytes()}))
    response = client.get(f"/api/v1/media/{asset.id}/image?width=500")
    assert response.status_code == 400


def test_demo_art_asset_and_unknown_ids_return_404(media_client):
    engine, owner, client = media_client
    demo = insert_asset(
        engine, source=MediaSource.PRELOADED, storage_key=f"demo-art/{uuid4()}"
    )
    try:
        install(client, engine, owner, FakeStorage())
        assert client.get(f"/api/v1/media/{demo.id}/image").status_code == 404
        assert client.get(f"/api/v1/media/{uuid4()}/image").status_code == 404
    finally:
        with engine.begin() as connection:
            connection.execute(delete(media_assets).where(media_assets.c.id == demo.id))


def test_another_users_asset_is_not_readable(media_client):
    engine, owner, client = media_client
    foreign_owner = User(display_name="Other owner", auth_provider_id=f"test-{uuid4()}")
    with engine.begin() as connection:
        connection.execute(insert(users).values(**foreign_owner.model_dump(by_alias=False)))
    foreign = insert_asset(engine, foreign_owner.id, storage_key="users/other/images/b.jpg")
    try:
        storage = FakeStorage({foreign.storage_key: jpeg_bytes()})
        install(client, engine, owner, storage)
        assert client.get(f"/api/v1/media/{foreign.id}/image").status_code == 404
        assert not storage.downloads
    finally:
        with engine.begin() as connection:
            connection.execute(delete(media_assets).where(media_assets.c.id == foreign.id))
            connection.execute(delete(users).where(users.c.id == foreign_owner.id))


def test_remote_url_asset_derives_from_the_hosted_original(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id, storage_key="https://cdn.example.com/photo.jpg")
    storage = FakeStorage(remote_objects={asset.storage_key: jpeg_bytes()})
    try:
        install(client, engine, owner, storage)
        response = client.get(f"/api/v1/media/{asset.id}/image?width=320")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"
        with Image.open(BytesIO(response.content)) as image:
            assert image.format == "WEBP"
            assert image.width <= 320
        assert storage.url_downloads == [asset.storage_key]
        assert asset.storage_key not in storage.downloads
    finally:
        with engine.begin() as connection:
            connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))


def test_remote_url_asset_reuses_its_hashed_derived_object(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id, storage_key="https://cdn.example.com/other.jpg")
    derived = ImageDerivatives(FakeStorage()).derived_key(asset.storage_key, 640)
    assert derived.startswith("derived/w640/remote/")
    storage = FakeStorage({derived: jpeg_bytes(640, 480)})
    try:
        install(client, engine, owner, storage)
        assert client.get(f"/api/v1/media/{asset.id}/image?width=640").status_code == 200
        assert not storage.url_downloads
    finally:
        with engine.begin() as connection:
            connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))


def test_remote_url_missing_on_the_host_returns_404(media_client):
    engine, owner, client = media_client
    asset = insert_asset(engine, owner.id, storage_key="https://cdn.example.com/gone.jpg")
    try:
        install(client, engine, owner, FakeStorage())
        assert client.get(f"/api/v1/media/{asset.id}/image").status_code == 404
    finally:
        with engine.begin() as connection:
            connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))
