from typing import Protocol
from uuid import UUID

from app.schemas.media import SceneObject


class SceneObjectNotFoundError(Exception):
    pass


class SceneObjectReviewConflictError(Exception):
    pass


class SceneObjectRepository(Protocol):
    def list_for_session(self, session_id: UUID, user_id: UUID) -> list[SceneObject]: ...
