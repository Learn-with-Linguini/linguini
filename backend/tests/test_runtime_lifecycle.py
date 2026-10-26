"""Shutdown keeps tracing and persistence available until background work finishes."""

from threading import Event

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services.background import ThreadPoolBackgroundRunner


class RecordingTracer:
    def __init__(self, events, *, fail=None):
        self.events = events
        self.fail = fail
        self.closed = False

    def flush(self):
        self.events.append("flush")
        if self.fail == "flush":
            raise RuntimeError("export failed")

    def shutdown(self):
        self.events.append("tracer-shutdown")
        self.closed = True
        if self.fail == "shutdown":
            raise RuntimeError("export failed")


class RecordingEngine:
    def __init__(self, events):
        self.events = events
        self.disposed = False

    def dispose(self):
        self.events.append("database-dispose")
        self.disposed = True


def configure_runtime(monkeypatch, events, *, fail=None):
    engine = RecordingEngine(events)
    tracer = RecordingTracer(events, fail=fail)
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setattr(main, "create_database_engine", lambda: engine)
    monkeypatch.setattr(main, "build_tracer", lambda _: tracer)
    monkeypatch.setattr(main, "build_object_grounder", lambda _: None)
    monkeypatch.setattr(main, "build_image_moderator", lambda _: None)
    return engine, tracer


def test_background_job_finishes_before_tracer_and_database_close(monkeypatch):
    events = []
    engine, tracer = configure_runtime(monkeypatch, events)
    started = Event()
    finishing = Event()

    class DrainingRunner(ThreadPoolBackgroundRunner):
        def shutdown(self, wait=True):
            finishing.set()
            super().shutdown(wait=wait)

    runner = DrainingRunner(max_workers=1)
    monkeypatch.setattr(main, "ThreadPoolBackgroundRunner", lambda: runner)

    def work():
        started.set()
        if finishing.wait(timeout=5):
            events.append(("job-finished", tracer.closed, engine.disposed))

    with TestClient(main.create_app()):
        runner.submit(work)
        assert started.wait(timeout=5)
    assert events == [
        ("job-finished", False, False), "flush", "tracer-shutdown", "database-dispose",
    ]


@pytest.mark.parametrize("failure", ["flush", "shutdown"])
def test_tracing_cleanup_failure_still_closes_database(monkeypatch, failure):
    events = []
    engine, tracer = configure_runtime(monkeypatch, events, fail=failure)

    with TestClient(main.create_app()):
        pass
    assert tracer.closed
    assert engine.disposed
    assert events == ["flush", "tracer-shutdown", "database-dispose"]
