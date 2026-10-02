"""Best-effort AI observability tracing.

Tracing is strictly best-effort: an unconfigured app gets ``NoOpAITracer``,
and every Langfuse SDK interaction is wrapped so a tracing failure can never
surface to a learner. ``record_content`` is the only door for input/output
payloads and drops everything unless ``capture_content`` is enabled; image
bytes, base64, keys, signed URLs, learner text and model responses are never
attached to an observation by any other path.
"""

import logging
import sys
import time
from collections.abc import Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from typing import Any, Protocol, runtime_checkable

from langfuse import Langfuse, propagate_attributes

from app.ai.settings import AiSettings

logger = logging.getLogger(__name__)


@runtime_checkable
class AIObservation(Protocol):
    def update(
        self,
        *,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        retry_count: int | None = None,
        validation_result: str | None = None,
        error_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None: ...

    def record_content(self, *, input: Any = None, output: Any = None) -> None: ...


@runtime_checkable
class AITracer(Protocol):
    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        feature: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[AIObservation]: ...

    def span(
        self, name: str, *, metadata: Mapping[str, Any] | None = None
    ) -> AbstractContextManager[AIObservation]: ...

    def generation(
        self,
        name: str,
        *,
        feature: str,
        provider: str,
        model: str,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_parameters: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[AIObservation]: ...

    def flush(self) -> None: ...

    def shutdown(self) -> None: ...


class _NoOpObservation:
    def update(self, **_: Any) -> None:
        return None

    def record_content(self, *, input: Any = None, output: Any = None) -> None:
        return None


_NOOP_OBSERVATION = _NoOpObservation()


class NoOpAITracer:
    """Tracer used when observability is disabled or misconfigured."""

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        feature: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        yield _NOOP_OBSERVATION

    @contextmanager
    def span(self, name: str, *, metadata: Mapping[str, Any] | None = None):
        yield _NOOP_OBSERVATION

    @contextmanager
    def generation(
        self,
        name: str,
        *,
        feature: str,
        provider: str,
        model: str,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_parameters: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        yield _NOOP_OBSERVATION

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


class _TracedObservation:
    """Wraps one SDK observation with our scalar-only update surface."""

    def __init__(self, observation: Any, capture_content: bool) -> None:
        self._observation = observation
        self._capture_content = capture_content
        self._latency_recorded = False

    def _update_raw(self, **kwargs: Any) -> None:
        try:
            self._observation.update(**kwargs)
        except Exception:
            logger.warning("Langfuse observation update failed", exc_info=True)

    def _fail(self, exc: BaseException) -> None:
        # Only the exception type name is recorded: str(exc) can contain
        # learner text, URLs or other payloads.
        self._update_raw(level="ERROR", status_message=type(exc).__name__)

    def update(
        self,
        *,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        retry_count: int | None = None,
        validation_result: str | None = None,
        error_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if latency_ms is not None:
            self._latency_recorded = True
        usage = {
            key: value
            for key, value in {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            }.items()
            if value is not None
        }
        meta = {
            key: value
            for key, value in {
                "latencyMs": latency_ms,
                "retryCount": retry_count,
                "validationResult": validation_result,
            }.items()
            if value is not None
        }
        if metadata:
            meta.update(metadata)
        kwargs: dict[str, Any] = {}
        if usage:
            kwargs["usage_details"] = usage
        if meta:
            kwargs["metadata"] = meta
        if error_code is not None:
            kwargs["level"] = "ERROR"
            kwargs["status_message"] = error_code
        if kwargs:
            self._update_raw(**kwargs)

    def record_content(self, *, input: Any = None, output: Any = None) -> None:
        if not self._capture_content:
            return
        kwargs: dict[str, Any] = {}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        if kwargs:
            self._update_raw(**kwargs)


class LangfuseAITracer:
    """AITracer backed by an already-constructed Langfuse client."""

    def __init__(self, client: Any, *, capture_content: bool = False) -> None:
        self._client = client
        self._capture_content = capture_content

    @contextmanager
    def _observe(
        self,
        as_type: str,
        name: str,
        *,
        session_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ):
        stack: ExitStack | None = None
        observation: Any = _NOOP_OBSERVATION
        started = time.perf_counter()
        try:
            stack = ExitStack()
            sdk_observation = stack.enter_context(
                self._client.start_as_current_observation(
                    as_type=as_type, name=name, **dict(extra or {})
                )
            )
            if session_id:
                stack.enter_context(propagate_attributes(session_id=session_id))
            observation = _TracedObservation(sdk_observation, self._capture_content)
        except Exception:
            logger.warning(
                "Langfuse observation setup failed; running untraced",
                exc_info=True,
            )
            if stack is not None:
                try:
                    stack.close()
                except Exception:
                    logger.warning(
                        "Langfuse observation cleanup failed", exc_info=True
                    )
                stack = None
        exc_info: tuple[Any, Any, Any] = (None, None, None)
        try:
            yield observation
        except Exception as exc:
            exc_info = sys.exc_info()
            if stack is not None:
                observation._fail(exc)
            raise
        finally:
            if stack is not None:
                if exc_info[0] is None and not observation._latency_recorded:
                    observation.update(
                        latency_ms=(time.perf_counter() - started) * 1000
                    )
                try:
                    stack.__exit__(*exc_info)
                except Exception:
                    logger.warning(
                        "Langfuse observation exit failed", exc_info=True
                    )

    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        feature: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        meta = dict(metadata or {})
        if feature is not None:
            meta["feature"] = feature
        return self._observe(
            "span", name, session_id=session_id, extra={"metadata": meta}
        )

    def span(self, name: str, *, metadata: Mapping[str, Any] | None = None):
        return self._observe("span", name, extra={"metadata": dict(metadata or {})})

    def generation(
        self,
        name: str,
        *,
        feature: str,
        provider: str,
        model: str,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        model_parameters: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        meta = {
            key: value
            for key, value in {
                "feature": feature,
                "provider": provider,
                "schemaVersion": schema_version,
            }.items()
            if value is not None
        }
        if metadata:
            meta.update(metadata)
        return self._observe(
            "generation",
            name,
            extra={
                "model": model,
                "model_parameters": dict(model_parameters or {}),
                "version": prompt_version,
                "metadata": meta,
            },
        )

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)

    def shutdown(self) -> None:
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)
        try:
            self._client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown failed", exc_info=True)


def _drop_content(*, data: Any, **_: Any) -> Any:
    return "[redacted]"


def build_tracer(settings: AiSettings) -> AITracer:
    """Construct the tracer for this process; never raises."""
    observability = settings.observability
    if not observability.enabled:
        return NoOpAITracer()
    if not observability.public_key or not observability.secret_key:
        # Real mode already failed in the loader; demo mode degrades quietly.
        logger.warning(
            "AI observability is enabled but Langfuse keys are missing; "
            "tracing disabled"
        )
        return NoOpAITracer()
    try:
        client = Langfuse(
            public_key=observability.public_key,
            secret_key=observability.secret_key,
            base_url=observability.base_url,
            environment=observability.environment,
            tracing_enabled=True,
            mask=None if observability.capture_content else _drop_content,
        )
        return LangfuseAITracer(
            client, capture_content=observability.capture_content
        )
    except Exception:
        logger.warning(
            "Langfuse client construction failed; tracing disabled",
            exc_info=True,
        )
        return NoOpAITracer()
