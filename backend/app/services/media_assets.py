import re
import warnings
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from app.repositories.media_assets import MediaAssetConflictError, MediaAssetRepository
from app.schemas.enums import MediaSource
from app.schemas.media import (
    MAX_IMAGE_BYTES,
    ConfirmMediaUploadRequest,
    CreateUploadUrlRequest,
    CreateUploadUrlResponse,
    MediaAsset,
    MediaAssetResponse,
)
from app.services.image_derivatives import ImageDerivatives
from app.services.image_storage import ImageStorage, InvalidImageUpload
from app.services.media_urls import MediaUrlError
from app.services.users import UserService


class MediaAssetNotFoundError(Exception):
    pass


class MediaAssetService:
    def __init__(
        self,
        repository: MediaAssetRepository,
        users: UserService,
        storage: ImageStorage | None = None,
        derivatives: ImageDerivatives | None = None,
    ) -> None:
        self.repository = repository
        self.users = users
        self.storage = storage
        self.derivatives = derivatives

    def _storage(self) -> ImageStorage:
        if self.storage is None:
            raise MediaUrlError("Storage is not configured.")
        return self.storage

    def _derivatives(self) -> ImageDerivatives:
        if self.derivatives is None:
            raise MediaUrlError("Image derivatives are not configured.")
        return self.derivatives

    def read_image(self, asset_id: UUID, width: int) -> bytes:
        asset = self.get_asset(asset_id)
        return self._derivatives().get(asset.storage_key, width)

    def _response(self, asset: MediaAsset) -> MediaAssetResponse:
        return MediaAssetResponse(
            **asset.model_dump(), signed_url=self._storage().read_url(asset.storage_key)
        )

    def read_asset(self, asset_id: UUID) -> MediaAssetResponse:
        return self._response(self.get_asset(asset_id))

    def create_upload(self, request: CreateUploadUrlRequest) -> CreateUploadUrlResponse:
        user = self.users.get_current_user()
        asset_id = uuid4()
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
            request.mime_type
        ]
        key = f"users/{user.id}/images/{asset_id}.{extension}"
        return CreateUploadUrlResponse(
            asset_id=asset_id,
            storage_key=key,
            upload_url=self._storage().upload_url(key),
            expires_in_seconds=7200,
        )

    def confirm_upload(self, request: ConfirmMediaUploadRequest) -> MediaAssetResponse:
        user = self.users.get_current_user()
        pattern = rf"users/{user.id}/images/{request.asset_id}\.(jpg|png|webp)"
        if not re.fullmatch(pattern, request.storage_key):
            raise InvalidImageUpload("Upload key does not match this user and asset.")
        existing = self.repository.get_by_ids([request.asset_id]).get(request.asset_id)
        if existing is not None:
            if existing.owner_user_id != user.id or existing.storage_key != request.storage_key:
                raise MediaAssetNotFoundError("Media asset not found.")
            return self._response(existing)
        storage = self._storage()
        try:
            data = storage.download(request.storage_key)
            if not data or len(data) > MAX_IMAGE_BYTES:
                raise InvalidImageUpload("Image must be between 1 byte and 10 MB.")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(data)) as image:
                        mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(
                            image.format
                        )
                        if mime is None:
                            raise InvalidImageUpload("Use a JPEG, PNG or WebP image.")
                        width, height = image.size
                        image.verify()
                    with Image.open(BytesIO(data)) as image:
                        image.load()
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                SyntaxError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as exc:
                raise InvalidImageUpload("The uploaded file is not a valid image.") from exc
        except InvalidImageUpload:
            storage.delete(request.storage_key)
            raise
        asset = MediaAsset(
            id=request.asset_id,
            owner_user_id=user.id,
            media_type="image",
            source=request.source,
            storage_key=request.storage_key,
            mime_type=mime,
            width=width,
            height=height,
        )
        try:
            asset = self.repository.create(asset)
        except MediaAssetConflictError:
            # Another confirmation may have committed while this one verified the bytes.
            existing = self.repository.get_by_ids([request.asset_id]).get(request.asset_id)
            if (
                existing is None
                or existing.owner_user_id != user.id
                or existing.storage_key != request.storage_key
            ):
                raise
            asset = existing
        return self._response(asset)

    def get_asset(self, asset_id: UUID) -> MediaAsset:
        user = self.users.get_current_user()
        asset = self.repository.get_by_ids([asset_id]).get(asset_id)
        if asset is None or not (
            asset.owner_user_id == user.id
            or (asset.owner_user_id is None and asset.source is MediaSource.PRELOADED)
        ):
            raise MediaAssetNotFoundError("Media asset not found.")
        return asset
