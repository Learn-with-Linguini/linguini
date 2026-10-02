from app.repositories.media_assets import MediaAssetStorageError
from app.repositories.scenes import SceneRepository
from app.schemas.enums import MediaSource
from app.schemas.media import PreloadedScene
from app.schemas.scenes import PreloadedSceneDetail
from app.services.media_urls import PrivateMediaUrls, public_media_url


class SceneNotFoundError(Exception):
    pass


class SceneService:
    def __init__(
        self,
        repository: SceneRepository,
        media_public_base_url: str | None = None,
        private_media_urls: PrivateMediaUrls | None = None,
    ) -> None:
        self.repository = repository
        self.media_public_base_url = media_public_base_url
        self.private_media_urls = private_media_urls

    def _hydrate_media(self, rows: list[PreloadedSceneDetail]) -> list[PreloadedSceneDetail]:
        # The repository join already validated each row's media asset.
        for row in rows:
            if row.media_asset.source is not MediaSource.PRELOADED:
                raise MediaAssetStorageError("Preloaded scene media is missing or not shared.")
        urls = (
            self.private_media_urls.resolve([row.media_asset.storage_key for row in rows])
            if self.private_media_urls is not None
            else {}
        )
        result = []
        for row in rows:
            asset = row.media_asset
            result.append(
                row.model_copy(
                    update={
                        "media_asset": asset,
                        "image_url": urls.get(asset.storage_key)
                        if self.private_media_urls
                        else public_media_url(asset.storage_key, self.media_public_base_url),
                    }
                )
            )
        return result

    def list_scenes(self, language_code: str | None = None) -> list[PreloadedScene]:
        return [
            PreloadedScene.model_validate(row.model_dump(include=set(PreloadedScene.model_fields)))
            for row in self._hydrate_media(
                [
                    row
                    for row in self.repository.list_scenes()
                    if language_code is None or row.language_code.lower() == language_code
                ]
            )
        ]

    def get_scene(self, scene_id: str, language_code: str | None = None) -> PreloadedSceneDetail:
        scene = next(
            (row for row in self.repository.list_scenes() if row.scene_id == scene_id), None
        )
        if scene is None or (
            language_code is not None and scene.language_code.lower() != language_code
        ):
            raise SceneNotFoundError("Scene not found.")
        return self._hydrate_media([scene])[0]
