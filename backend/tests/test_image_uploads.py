from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.dependencies import get_media_asset_service
from app.main import create_app
from app.repositories.media_assets import MediaAssetConflictError
from app.schemas.media import (
    MAX_IMAGE_BYTES,
    ConfirmMediaUploadRequest,
    CreateUploadUrlRequest,
    MediaAsset,
)
from app.schemas.users import User
from app.services.image_storage import InvalidImageUpload, UploadObjectMissing
from app.services.media_assets import MediaAssetNotFoundError, MediaAssetService


@pytest.fixture
def setup():
    user = User(display_name="Upload tester", auth_provider_id="demo-test")
    users = MagicMock()
    users.get_current_user.return_value = user
    repo = MagicMock()
    rows = {}
    repo.get_by_ids.side_effect = lambda ids: {id: rows[id] for id in ids if id in rows}

    def create(asset):
        rows[asset.id] = asset
        return asset

    repo.create.side_effect = create
    storage = MagicMock()
    storage.upload_url.return_value = "https://example.com/upload?token=test"
    storage.read_url.return_value = "https://example.com/read?token=test"
    service = MediaAssetService(repo, users, storage)
    return service, user, repo, storage, rows


def request_for(user, **kwargs):
    asset_id = uuid4()
    return ConfirmMediaUploadRequest(
        asset_id=asset_id,
        storage_key=f"users/{user.id}/images/{asset_id}.jpg",
        source="camera",
        **kwargs,
    )


def image_bytes(format="PNG"):
    data = BytesIO()
    Image.new("RGB", (23, 17), "blue").save(data, format=format)
    return data.getvalue()


def test_upload_key_ignores_filename_and_does_not_create_asset(setup):
    service, user, repo, storage, _ = setup
    result = service.create_upload(
        CreateUploadUrlRequest(
            file_name="../../malicious.exe",
            file_size=10,
            mime_type="image/png",
            source="userUpload",
        )
    )
    assert result.storage_key == f"users/{user.id}/images/{result.asset_id}.png"
    assert result.expires_in_seconds == 7200
    repo.create.assert_not_called()
    storage.upload_url.assert_called_once_with(result.storage_key)


@pytest.mark.parametrize(
    "format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_confirm_derives_metadata_and_is_idempotent(setup, format, mime):
    service, user, repo, storage, _ = setup
    request = request_for(user)
    storage.download.return_value = image_bytes(format)
    first = service.confirm_upload(request)
    second = service.confirm_upload(request)
    assert first.id == second.id == request.asset_id
    assert (first.mime_type, first.width, first.height) == (mime, 23, 17)
    assert first.owner_user_id == user.id
    assert first.expires_in_seconds == 3600
    repo.create.assert_called_once()
    storage.download.assert_called_once()
    storage.delete.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        b"x" * (MAX_IMAGE_BYTES + 1),
        image_bytes("GIF"),
        image_bytes("JPEG")[:40],
    ],
    ids=["empty", "non-image", "oversized", "unsupported-gif", "truncated-jpeg"],
)
def test_invalid_image_is_deleted_without_metadata(setup, data):
    service, user, repo, storage, _ = setup
    request = request_for(user)
    storage.download.return_value = data
    with pytest.raises(InvalidImageUpload):
        service.confirm_upload(request)
    storage.delete.assert_called_once_with(request.storage_key)
    repo.create.assert_not_called()


def test_stream_size_limit_failure_also_deletes(setup):
    service, user, repo, storage, _ = setup
    storage.download.side_effect = InvalidImageUpload("too large")
    request = request_for(user)
    with pytest.raises(InvalidImageUpload):
        service.confirm_upload(request)
    storage.delete.assert_called_once_with(request.storage_key)
    repo.create.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [
        "users/other/images/x.jpg",
        "preloaded/scenes/cafe.jpg",
        "users/{user}/images/{asset}.jpg/../x",
        "users/{user}/images/other.jpg",
    ],
)
def test_invalid_key_never_reads_or_deletes_storage(setup, key):
    service, user, repo, storage, _ = setup
    request = request_for(user)
    request.storage_key = key.format(user=user.id, asset=request.asset_id)
    with pytest.raises(InvalidImageUpload):
        service.confirm_upload(request)
    storage.download.assert_not_called()
    storage.delete.assert_not_called()
    repo.create.assert_not_called()


def test_missing_object_does_not_insert_or_delete(setup):
    service, user, repo, storage, _ = setup
    storage.download.side_effect = UploadObjectMissing()
    with pytest.raises(UploadObjectMissing):
        service.confirm_upload(request_for(user))
    repo.create.assert_not_called()
    storage.delete.assert_not_called()


def test_concurrent_confirm_returns_winner(setup):
    service, user, repo, storage, rows = setup
    request = request_for(user)
    storage.download.return_value = image_bytes()

    def winner(asset):
        rows[asset.id] = asset
        raise MediaAssetConflictError()

    repo.create.side_effect = winner
    assert service.confirm_upload(request).id == request.asset_id


def test_read_hides_foreign_assets_and_signs_owned_and_preloaded(setup):
    service, user, _, storage, rows = setup
    shared = MediaAsset(
        source="preloaded", media_type="image", storage_key="preloaded/p.png", mime_type="image/png"
    )
    owned = MediaAsset(
        source="camera",
        owner_user_id=user.id,
        media_type="image",
        storage_key="mine.png",
        mime_type="image/png",
    )
    foreign = owned.model_copy(update={"id": uuid4(), "owner_user_id": uuid4()})
    rows.update({a.id: a for a in [shared, owned, foreign]})
    for id in [foreign.id, uuid4()]:
        with pytest.raises(MediaAssetNotFoundError):
            service.read_asset(id)
    storage.read_url.assert_not_called()
    assert service.read_asset(owned.id).signed_url
    assert service.read_asset(shared.id).signed_url


@pytest.mark.parametrize(
    "patch",
    [
        {"fileSize": 0},
        {"fileSize": -1},
        {"fileSize": MAX_IMAGE_BYTES + 1},
        {"fileSize": True},
        {"mimeType": "image/gif"},
        {"source": "preloaded"},
    ],
)
def test_api_rejects_invalid_upload_request(setup, patch):
    service, _, repo, storage, _ = setup
    app = create_app()
    app.dependency_overrides[get_media_asset_service] = lambda: service
    response = TestClient(app).post(
        "/api/v1/media/upload-url",
        json={
            "fileName": "photo.jpg",
            "fileSize": 1,
            "mimeType": "image/jpeg",
            "source": "camera",
            **patch,
        },
    )
    assert response.status_code == 422
    storage.upload_url.assert_not_called()
    repo.create.assert_not_called()
