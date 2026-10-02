"""Tracing wrappers for AI collaborators.

Each wrapper preserves the inner collaborator's public behaviour — return
values, exceptions and error semantics are unchanged — while recording one
observation per call through an AITracer.
"""

from typing import Any

from app.ai.observability import AITracer
from app.ai.settings import AiFeature
from app.schemas.ispy_guess import ISpyGuessResult
from app.services.ispy_guess import ISpyGuessError


class TracedISpyGuessGenerator:
    """Wraps the I-Spy description evaluator in one generation observation."""

    def __init__(
        self,
        inner: Any,
        tracer: AITracer,
        *,
        provider: str,
        model: str,
        max_retries: int = 0,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        self._provider = provider
        self._model = model
        self._max_retries = max_retries

    def guess(self, context: dict[str, Any], learner_text: str) -> ISpyGuessResult:
        with self._tracer.generation(
            "ispy-description-evaluation",
            feature=AiFeature.ISPY_GUESS.value,
            provider=self._provider,
            model=self._model,
        ) as observation:
            try:
                result = self._inner.guess(context, learner_text)
            except ISpyGuessError as exc:
                observation.update(
                    validation_result="invalid",
                    error_code=type(exc).__name__,
                    retry_count=self._max_retries,
                )
                raise
            observation.update(
                validation_result="valid", retry_count=self._max_retries
            )
            observation.record_content(
                input={"learnerText": learner_text},
                output=result.model_dump(mode="json", by_alias=True),
            )
            return result
