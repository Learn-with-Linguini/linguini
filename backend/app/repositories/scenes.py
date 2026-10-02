from typing import Protocol

from app.schemas.scenes import PreloadedSceneDetail


class SceneStorageError(Exception):
    pass


class SceneRepository(Protocol):
    def list_scenes(self) -> list[PreloadedSceneDetail]: ...
