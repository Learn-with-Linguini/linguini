import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.api.dependencies import get_active_language, get_media_asset_service, get_scene_service
from app.schemas.media import (
    ConfirmMediaUploadRequest,
    CreateUploadUrlRequest,
    CreateUploadUrlResponse,
    MediaAssetResponse,
    PreloadedScene,
)
from app.schemas.scenes import PreloadedSceneCatalogDetail
from app.services.image_derivatives import ALLOWED_WIDTHS
from app.services.media_assets import MediaAssetService
from app.services.scenes import SceneService

router = APIRouter(tags=["media"])


@router.get("/media/{asset_id}", response_model=MediaAssetResponse)
def get_media_asset(
    asset_id: UUID,
    service: Annotated[MediaAssetService, Depends(get_media_asset_service)],
) -> MediaAssetResponse:
    return service.read_asset(asset_id)


IMAGE_CACHE_HEADERS = "private, max-age=31536000, immutable"


@router.get("/media/{asset_id}/image")
def get_media_image(
    asset_id: UUID,
    service: Annotated[MediaAssetService, Depends(get_media_asset_service)],
    if_none_match: Annotated[str | None, Header()] = None,
    width: Annotated[int, Query()] = 640,
) -> Response:
    if width not in ALLOWED_WIDTHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_width",
                "message": "Width must be one of 320, 640 or 1280.",
            },
        )
    data = service.read_image(asset_id, width)
    etag = f'"{hashlib.sha256(data).hexdigest()}"'
    headers = {"Cache-Control": IMAGE_CACHE_HEADERS, "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=data, media_type="image/webp", headers=headers)


@router.post("/media/upload-url", response_model=CreateUploadUrlResponse)
def create_upload_url(
    request: CreateUploadUrlRequest,
    service: Annotated[MediaAssetService, Depends(get_media_asset_service)],
) -> CreateUploadUrlResponse:
    return service.create_upload(request)


@router.post(
    "/media/confirm-upload",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_upload(
    request: ConfirmMediaUploadRequest,
    service: Annotated[MediaAssetService, Depends(get_media_asset_service)],
) -> MediaAssetResponse:
    return service.confirm_upload(request)


@router.get("/preloaded-scenes", response_model=list[PreloadedScene])
def list_preloaded_scenes(
    service: Annotated[SceneService, Depends(get_scene_service)],
    language: Annotated[str, Depends(get_active_language)],
) -> list[PreloadedScene]:
    return service.list_scenes(language)


@router.get("/preloaded-scenes/{scene_id}", response_model=PreloadedSceneCatalogDetail)
def get_preloaded_scene(
    scene_id: str,
    service: Annotated[SceneService, Depends(get_scene_service)],
    language: Annotated[str, Depends(get_active_language)],
) -> PreloadedSceneCatalogDetail:
    detail = service.get_scene(scene_id, language)
    return PreloadedSceneCatalogDetail.model_validate(
        detail.model_dump(include=set(PreloadedSceneCatalogDetail.model_fields))
    )
