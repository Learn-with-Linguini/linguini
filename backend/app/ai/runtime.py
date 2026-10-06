"""Application-scoped AI feature services shared by every request."""

import threading
from collections.abc import Callable
from typing import Any

from app.ai.observability import AITracer
from app.ai.registry import (
    build_ispy_clue_generator,
    build_ispy_guess_generator,
    build_learning_task_generator,
    build_scene_translator,
    build_uploaded_scene_analyzer,
)
from app.ai.settings import AiSettings
from app.services.image_storage import ImageStorage


class AiRuntime:
    """Builds each configured feature service, and its provider client, once.

    Services are built on first use, so requests that never call a model, such
    as session polling, never construct OpenAI or Gemini clients.
    """

    def __init__(
        self,
        settings: AiSettings,
        tracer: AITracer,
        *,
        storage: ImageStorage | None = None,
        object_grounder: Any = None,
        image_moderator: Any = None,
    ) -> None:
        self.settings = settings
        self.tracer = tracer
        self._storage = storage
        self._object_grounder = object_grounder
        self._image_moderator = image_moderator
        self._services: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _service(self, name: str, build: Callable[[], Any]) -> Any:
        with self._lock:
            if name not in self._services:
                self._services[name] = build()
            return self._services[name]

    def uploaded_scene_analyzer(self):
        return self._service(
            "uploaded_scene_analyzer",
            lambda: build_uploaded_scene_analyzer(
                self.settings,
                self._storage,
                self.tracer,
                object_grounder=self._object_grounder,
                image_moderator=self._image_moderator,
            ),
        )

    def translator(self):
        return self._service(
            "translator", lambda: build_scene_translator(self.settings, self.tracer)
        )

    def learning_task_generator(self):
        return self._service(
            "learning_task_generator",
            lambda: build_learning_task_generator(self.settings, self.tracer),
        )

    def ispy_clue_generator(self):
        return self._service(
            "ispy_clue_generator",
            lambda: build_ispy_clue_generator(self.settings, self.tracer),
        )

    def ispy_guess_generator(self):
        return self._service(
            "ispy_guess_generator",
            lambda: build_ispy_guess_generator(self.settings, self.tracer),
        )
