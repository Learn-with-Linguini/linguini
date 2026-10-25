"""Validated lesson and clue templates for precomputed preloaded scenes.

Each stage runs the normal routed feature service on the exact payload a
learner session builds when every curated object is accepted unchanged, and
stores the validated result under ``content["generated"]``.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.ai.cache import GENERATED_CONTENT_KEY, TemplateMissing, TemplateSet
from app.ai.observability import NoOpAITracer
from app.ai.settings import AiFeature, AiSettings
from app.repositories.postgres.workflow import (
    ispy_clue_payload,
    learning_task_payload,
    translation_payload,
)
from app.services.scene_analysis import curated_relations, scene_summary
from app.services.session_plan import curated_scene_object

STAGE_FEATURES = {
    "translation": AiFeature.SCENE_TRANSLATION,
    "lessons": AiFeature.LEARNING_TASK,
    "clues": AiFeature.ISPY_CLUE,
}
STAGES = tuple(STAGE_FEATURES)


class CallCountingTracer(NoOpAITracer):
    """Counts outbound routed model calls (one ``model-call`` span each)."""

    def __init__(self) -> None:
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def span(self, name: str, *, metadata: Mapping[str, Any] | None = None):
        if name == "model-call":
            with self._lock:
                self._calls += 1
        return super().span(name, metadata=metadata)


class CallBudget:
    """A run-wide provider-call cap; ``limit=None`` is unlimited.

    A step starts only when its worst-case call count still fits.
    """

    def __init__(self, limit: int | None, tracer: CallCountingTracer) -> None:
        self.limit = limit
        self._tracer = tracer
        self._unrouted = 0

    @property
    def used(self) -> int:
        return self._tracer.calls + self._unrouted

    def allows(self, calls: int) -> bool:
        return self.limit is None or self.used + calls <= self.limit

    def add_unrouted(self, calls: int) -> None:
        self._unrouted += calls


@dataclass(frozen=True)
class StageOutcome:
    """One report line; never carries scene text, provider bodies or secrets."""

    slug: str
    language: str
    stage: str
    status: str
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def route_calls(settings: AiSettings, feature: AiFeature) -> int:
    """The most outbound calls one invocation of ``feature`` can make."""
    route = settings.ai_config.routes.get(feature) if settings.ai_config else None
    if route is not None and route.max_model_calls:
        return route.max_model_calls
    return 1 + settings.feature(feature).max_retries


def error_code(error: BaseException) -> str:
    """A sanitized code for ``error``: the provider code if any, else its type."""
    current: BaseException | None = error
    while current is not None:
        code = getattr(current, "code", None)
        if code is not None:
            return str(getattr(code, "value", code))
        current = current.__cause__
    return type(error).__name__


def curated_generation_inputs(
    row: Mapping[str, Any], language: str, session_id: UUID | None = None
):
    """The translation payload, objects and relations a ``language`` session of ``row`` builds."""
    session_id = session_id or uuid5(NAMESPACE_URL, f"linguini:preloaded-template:{row['slug']}")
    scene = {
        "title": row["title"],
        "description": row["description"],
        "content": row["content"],
    }
    objects = [curated_scene_object(session_id, entry) for entry in row["content"]["items"]]
    relations = curated_relations(scene, objects)
    payload = translation_payload(
        language,
        row["title"],
        scene_summary(scene, objects) or "Confirmed scene vocabulary.",
        objects,
        relations,
    )
    return payload, objects, relations


def generate_row_templates(
    row: dict[str, Any],
    language: str,
    services: Mapping[str, Any],
    budget: CallBudget,
    reserve: Mapping[str, int],
    *,
    stages: frozenset[str] = frozenset(STAGES),
    force: bool = False,
) -> list[StageOutcome]:
    """Fill ``row["content"]["generated"]`` for ``language``; reuse templates that still match.

    Templates for other languages are kept: each is keyed by its target language.

    Lessons and clues depend on the translation, so they run only when a
    translation is generated or reused for the same scene facts. A language with a
    ready pack gets the pack translation with its lesson and clues, which lessons and
    I-Spy games both use; a language without one gets the unguided set.
    """
    from app.language_packs.context import resolve_language_context

    payload, objects, relations = curated_generation_inputs(row, language)
    current = TemplateSet.from_content([row["content"]]).templates
    outcomes = []
    context = resolve_language_context(language)
    passes = [("pack-", context, STAGES) if context is not None else ("", None, STAGES)]

    for prefix, language_context, pass_stages in passes:
        translated = None
        options = {"language_context": language_context} if language_context else {}

        def outcome(stage, status, reason=None, prefix=prefix):
            outcomes.append(StageOutcome(row["slug"], language, f"{prefix}{stage}", status, reason))

        for stage in pass_stages:
            service = services.get(stage)
            if service is None:
                outcome(stage, "missing", "notConfigured")
                continue
            if stage != "translation" and translated is None:
                outcome(stage, "missing", "translationMissing")
                continue
            selected = stage in stages
            # A pack translation also runs its meaning review.
            calls = reserve[stage] * (2 if language_context and stage == "translation" else 1)
            templates = TemplateSet(
                current,
                reuse=not (force and selected),
                generate=selected and budget.allows(calls),
                record=True,
            )
            before = budget.used
            try:
                if stage == "translation":
                    translated = service.translate(payload, templates=templates, **options)
                elif stage == "lessons":
                    service.generate(
                        learning_task_payload(payload, translated, relations),
                        templates=templates,
                    )
                else:
                    service.generate(
                        ispy_clue_payload(payload, translated, objects, relations),
                        templates=templates,
                    )
            except TemplateMissing:
                outcome(stage, "missing", "callBudget" if selected else "notSelected")
                continue
            except Exception as error:
                outcome(stage, "failed", error_code(error))
                continue
            current = templates.templates
            if templates.recorded:
                outcome(stage, "generated")
            elif budget.used > before:
                outcome(stage, "failed", "templateNotStored")
            else:
                outcome(stage, "reused")
    if current:
        row["content"][GENERATED_CONTENT_KEY] = TemplateSet(current).content()
    return outcomes
