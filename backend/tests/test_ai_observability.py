"""Tests for the AI observability seam — never contacts Langfuse."""

from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.ai import (
    AIObservation,
    AITracer,
    LangfuseAITracer,
    NoOpAITracer,
    build_tracer,
    load_ai_settings,
)
from app.ai.features.ispy_guess import ISpyGuessError


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


def test_fake_tracer_satisfies_protocol():
    assert isinstance(FakeTracer(), AITracer)
    assert isinstance(FakeObservation([]), AIObservation)


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


@pytest.fixture
def sdk_tracer(monkeypatch):
    """Exercise real SDK serialization with an exporter that never sends HTTP."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()

    def create_client(**kwargs):
        return Langfuse(**kwargs, tracer_provider=provider, span_exporter=exporter)

    monkeypatch.setattr("app.ai.observability.Langfuse", create_client)
    settings = load_ai_settings(env={
        "AI_OBSERVABILITY_ENABLED": "true",
        "AI_OBSERVABILITY_PUBLIC_KEY": f"pk-lf-test-{uuid4()}",
        "AI_OBSERVABILITY_SECRET_KEY": "sk-lf-test-only",
    })
    tracer = build_tracer(settings)
    assert isinstance(tracer, LangfuseAITracer)
    yield tracer, exporter
    tracer.shutdown()
    provider.shutdown()


def test_sdk_exports_diagnostics_without_payloads_or_exception_details(sdk_tracer):
    tracer, exporter = sdk_tracer
    secret = "learner-sentinel https://signed.example/photo?token=secret"
    original = ValueError(secret)
    with pytest.raises(ValueError) as caught:
        with tracer.trace("scene-analysis", session_id="session-privacy", metadata={
            "objectCount": 3, "rawLearnerText": secret,
        }):
            with tracer.generation(
                "model-call", feature="sceneAnalysis", provider="openrouter",
                model="requested-model", prompt_version="scene.v1",
                metadata={"deployment": "primary", "attempt": 1},
            ) as observation:
                observation.record_content(input={"objectCount": secret}, output=secret)
                observation.update(error_code="providerTimeout", retry_count=0)
                raise original
    assert caught.value is original
    tracer.flush()
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {"scene-analysis", "model-call"}
    root = next(span for span in spans if span.name == "scene-analysis")
    child = next(span for span in spans if span.name == "model-call")
    assert child.parent.span_id == root.context.span_id
    assert root.context.trace_id == child.context.trace_id
    assert root.attributes["langfuse.observation.metadata.objectCount"] == 3
    assert child.attributes["langfuse.observation.metadata.deployment"] == "primary"
    assert child.attributes["langfuse.observation.metadata.retryCount"] == 0
    assert root.status.description == "ValueError"
    assert child.status.description == "providerTimeout"
    for span in spans:
        assert span.attributes["session.id"] == "session-privacy"
        assert not span.events
        exported = repr((dict(span.attributes), span.status.description, span.events))
        assert secret not in exported
        assert "rawLearnerText" not in exported
        assert "exception.stacktrace" not in exported


def test_sdk_only_outbound_generations_own_usage_after_failover(sdk_tracer):
    from test_routing import TIMEOUT, Route, translator
    from test_scene_translation_service import PAYLOAD, VALID_OUTPUT

    tracer, exporter = sdk_tracer
    route = Route(
        {"primary": ["a"], "backup": ["b"]},
        {("primary", "a"): [TIMEOUT], ("backup", "b"): [VALID_OUTPUT]},
    )
    route.tracer = tracer
    route.client._tracer = tracer
    with tracer.trace("practice", session_id="session-usage"):
        translator(route).translate(PAYLOAD)
    tracer.flush()
    spans = exporter.get_finished_spans()
    generations = [span for span in spans
                   if span.attributes.get("langfuse.observation.type") == "generation"]
    assert len(generations) == 2
    assert all(span.name == "model-call" for span in generations)
    failed, served = generations
    assert failed.attributes["langfuse.observation.model.name"] == "model-primary"
    assert failed.status.description == "providerTimeout"
    assert served.attributes["langfuse.observation.model.name"] == "served"
    assert served.attributes["langfuse.observation.usage_details"] == (
        '{"input": 3, "output": 4, "total": 7}'
    )
    feature = next(span for span in spans if span.name == "scene-translation")
    assert feature.attributes["langfuse.observation.type"] == "span"
    assert "langfuse.observation.usage_details" not in feature.attributes
    assert feature.attributes["langfuse.observation.metadata.promptVersion"]
    assert feature.attributes["langfuse.observation.metadata.totalTokens"] == 7
    assert all(span.attributes["session.id"] == "session-usage" for span in spans)


def test_sdk_update_and_exit_errors_preserve_the_application_exception(caplog):
    class BrokenObservation:
        def update(self, **kwargs):
            raise RuntimeError("sdk-secret")

    class BrokenClient:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            try:
                yield BrokenObservation()
            finally:
                raise RuntimeError("sdk-secret")

    original = ValueError("learner-secret")
    with pytest.raises(ValueError) as caught:
        with LangfuseAITracer(BrokenClient()).span("work"):
            raise original
    assert caught.value is original
    assert "sdk-secret" not in caplog.text
    assert "learner-secret" not in caplog.text
