"""Tests for the AI observability seam — never contacts Langfuse."""

from contextlib import contextmanager
from typing import Any

import pytest

from app.ai import (
    AIObservation,
    AITracer,
    LangfuseAITracer,
    NoOpAITracer,
    build_tracer,
    load_ai_settings,
)
from app.ai.instrumentation import TracedISpyGuessGenerator
from app.schemas.ispy_guess import ISpyGuessResult
from app.services.ispy_guess import ISpyGuessError


class FakeObservation:
    def __init__(self, record: list[tuple[str, dict[str, Any]]]) -> None:
        self.record = record

    def update(self, **kwargs: Any) -> None:
        self.record.append(("update", kwargs))

    def record_content(self, **kwargs: Any) -> None:
        self.record.append(("content", kwargs))


class FakeTracer:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []
        self.observation = FakeObservation(self.records)

    @contextmanager
    def generation(self, name: str, **kwargs: Any):
        self.records.append(("generation", {"name": name, **kwargs}))
        yield self.observation

    @contextmanager
    def trace(self, name: str, **kwargs: Any):
        self.records.append(("trace", {"name": name, **kwargs}))
        yield self.observation

    @contextmanager
    def span(self, name: str, **kwargs: Any):
        self.records.append(("span", {"name": name, **kwargs}))
        yield self.observation

    def flush(self) -> None:
        self.records.append(("flush", {}))

    def shutdown(self) -> None:
        self.records.append(("shutdown", {}))


class StubInner:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[dict[str, Any], str]] = []

    def guess(self, context, learner_text):
        self.calls.append((context, learner_text))
        if self.error is not None:
            raise self.error
        return self.result


def _result() -> ISpyGuessResult:
    return ISpyGuessResult.model_validate(
        {
            "guessed_object_key": "cup",
            "ambiguous": False,
            "feedback": "Good description.",
        }
    )


def _generator(tracer, inner):
    return TracedISpyGuessGenerator(
        inner, tracer, provider="openai", model="gpt-4o-mini", max_retries=0
    )


def test_fake_tracer_satisfies_protocol():
    assert isinstance(FakeTracer(), AITracer)
    assert isinstance(FakeObservation([]), AIObservation)


def test_traced_guess_success_records_generation():
    tracer = FakeTracer()
    inner = StubInner(result=_result())
    generator = _generator(tracer, inner)
    result = generator.guess({"scene": "desk"}, "it is the red cup")
    assert result == inner.result
    (kind, call), *rest = tracer.records
    assert kind == "generation"
    assert call["name"] == "ispy-description-evaluation"
    assert call["feature"] == "ispyGuess"
    assert call["provider"] == "openai"
    assert call["model"] == "gpt-4o-mini"
    updates = [kw for tag, kw in rest if tag == "update"]
    assert any(u.get("validation_result") == "valid" for u in updates)


def test_traced_guess_error_records_invalid_and_reraises():
    tracer = FakeTracer()
    inner = StubInner(error=ISpyGuessError("bad guess"))
    generator = _generator(tracer, inner)
    with pytest.raises(ISpyGuessError):
        generator.guess({}, "guess")
    updates = [
        kw for tag, kw in tracer.records if tag == "update" and kw
    ]
    failing = [
        u for u in updates if u.get("validation_result") == "invalid"
    ]
    assert failing and failing[0]["error_code"] == "ISpyGuessError"


def test_content_dropped_unless_capture_opted_in():
    """The real _TracedObservation.record_content gate is the privacy seam."""
    learner_text = "the blue notebook on the table"
    feedback = "Good description."

    client = RecordingClient()
    tracer = LangfuseAITracer(client, capture_content=False)
    _generator(tracer, StubInner(result=_result())).guess({}, learner_text)
    recorded = repr((client.calls, client.updates))
    assert learner_text not in recorded
    assert feedback not in recorded

    client = RecordingClient()
    tracer = LangfuseAITracer(client, capture_content=True)
    _generator(tracer, StubInner(result=_result())).guess({}, learner_text)
    payloads = [u for u in client.updates if "input" in u or "output" in u]
    assert payloads
    assert payloads[0]["input"] == {"learnerText": learner_text}
    assert feedback in repr(client.updates)


def test_noop_tracer_satisfies_protocol_and_contexts_work():
    tracer = NoOpAITracer()
    assert isinstance(tracer, AITracer)
    with tracer.trace("t", session_id="s", feature="f") as obs:
        obs.update(latency_ms=1, error_code="x")
        obs.record_content(input="anything")
    with tracer.span("s") as obs:
        assert isinstance(obs, AIObservation)
    with tracer.generation(
        "g", feature="ispyGuess", provider="openai", model="m"
    ) as obs:
        obs.update(input_tokens=1, output_tokens=2, total_tokens=3)
    tracer.flush()
    tracer.shutdown()


class ExplodingClient:
    def start_as_current_observation(self, **kwargs):
        raise RuntimeError("boom")

    def flush(self):
        raise RuntimeError("boom")

    def shutdown(self):
        raise RuntimeError("boom")


def test_langfuse_tracer_never_escalates_sdk_failures():
    tracer = LangfuseAITracer(ExplodingClient())
    ran = []
    with tracer.generation(
        "g", feature="ispyGuess", provider="openai", model="m"
    ) as obs:
        ran.append(True)
        obs.update(validation_result="valid")
        obs.record_content(input="x")
    assert ran == [True]
    tracer.flush()
    tracer.shutdown()
    # Exceptions inside the body still propagate even if exit also fails.
    with pytest.raises(ValueError):
        with tracer.span("s"):
            raise ValueError("inner")


class RecordingSdkObservation:
    def __init__(self, client):
        self.client = client

    def update(self, **kwargs):
        self.client.updates.append(kwargs)


class RecordingClient:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.flushed = 0
        self.closed = 0

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.calls.append(kwargs)
        try:
            yield RecordingSdkObservation(self)
        finally:
            self.closed += 1

    def flush(self):
        self.flushed += 1

    def shutdown(self):
        self.flushed += 1
        self.closed += 100


def test_langfuse_tracer_maps_dimensions_to_sdk():
    client = RecordingClient()
    tracer = LangfuseAITracer(client, capture_content=True)
    with tracer.generation(
        "ispy-description-evaluation",
        feature="ispyGuess",
        provider="openai",
        model="gpt-4o-mini",
        prompt_version="v1",
        model_parameters={"temperature": 0},
        metadata={"extra": "yes"},
    ) as obs:
        obs.update(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            validation_result="valid",
            retry_count=1,
        )
    call = client.calls[0]
    assert call["as_type"] == "generation"
    assert call["name"] == "ispy-description-evaluation"
    assert call["model"] == "gpt-4o-mini"
    assert call["version"] == "v1"
    assert call["metadata"]["feature"] == "ispyGuess"
    assert call["metadata"]["provider"] == "openai"
    update = client.updates[0]
    assert update["usage_details"] == {"input": 10, "output": 5, "total": 15}
    assert update["metadata"]["validationResult"] == "valid"
    assert update["metadata"]["retryCount"] == 1
    # Auto-latency recorded on normal exit.
    assert any(
        "latencyMs" in u.get("metadata", {}) for u in client.updates
    )
    assert client.closed == 1


def test_langfuse_tracer_trace_propagates_session_id():
    client = RecordingClient()
    tracer = LangfuseAITracer(client)
    ran = []
    with tracer.trace(
        "session-work", session_id="session-123", feature="ispyGuess"
    ) as obs:
        ran.append(True)
        obs.update(validation_result="valid")
    assert ran == [True]
    assert client.calls[0]["as_type"] == "span"
    assert client.calls[0]["metadata"]["feature"] == "ispyGuess"
    assert client.closed == 1


def test_langfuse_tracer_records_error_class_name_only():
    client = RecordingClient()
    tracer = LangfuseAITracer(client)
    with pytest.raises(ISpyGuessError):
        with tracer.generation(
            "g", feature="ispyGuess", provider="openai", model="m"
        ):
            raise ISpyGuessError("secret learner text")
    errors = [u for u in client.updates if u.get("level") == "ERROR"]
    assert errors and errors[0]["status_message"] == "ISpyGuessError"
    assert "secret learner text" not in repr(client.updates)


def test_langfuse_tracer_error_code_update_sets_error_level():
    client = RecordingClient()
    tracer = LangfuseAITracer(client)
    with tracer.span("s") as obs:
        obs.update(error_code="ISpyGuessError")
    errors = [u for u in client.updates if u.get("level") == "ERROR"]
    assert errors and errors[0]["status_message"] == "ISpyGuessError"


def test_build_tracer_disabled_and_missing_keys_return_noop():
    settings = load_ai_settings(env={})
    assert isinstance(build_tracer(settings), NoOpAITracer)
    demo_missing_keys = load_ai_settings(
        env={
            "AI_MODE": "demo",
            "AI_OBSERVABILITY_ENABLED": "true",
        }
    )
    assert isinstance(build_tracer(demo_missing_keys), NoOpAITracer)
