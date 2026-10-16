import logging
from unittest.mock import MagicMock

from app.ai.observability import NoOpAITracer
from app.ai.runtime import AiRuntime
from app.ai.settings import load_ai_settings


def test_uploaded_scene_analyzer_logs_unconfigured_state_once(caplog):
    caplog.set_level(logging.INFO, logger="app.ai.registry")
    caplog.set_level(logging.INFO, logger="app.ai.runtime")
    runtime = AiRuntime(
        load_ai_settings(env={"AI_MODE": "demo"}),
        NoOpAITracer(),
        storage=MagicMock(),
    )

    assert runtime.uploaded_scene_analyzer() is None
    first_record_count = len(caplog.records)
    assert any(
        record.name == "app.ai.registry"
        and record.levelno == logging.WARNING
        and "AI_OPENROUTER_API_KEY" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        record.name == "app.ai.runtime"
        and record.levelno == logging.WARNING
        and "placeholder" in record.getMessage()
        for record in caplog.records
    )

    assert runtime.uploaded_scene_analyzer() is None
    assert len(caplog.records) == first_record_count


def test_uploaded_scene_analyzer_logs_construction_without_secret(caplog):
    caplog.set_level(logging.INFO, logger="app.ai.registry")
    caplog.set_level(logging.INFO, logger="app.ai.runtime")
    runtime = AiRuntime(
        load_ai_settings(
            env={"AI_MODE": "demo", "AI_OPENROUTER_API_KEY": "sk-test"}
        ),
        NoOpAITracer(),
        storage=MagicMock(),
    )

    assert runtime.uploaded_scene_analyzer() is not None
    assert any(
        record.name == "app.ai.runtime"
        and record.levelno == logging.INFO
        and "constructed" in record.getMessage()
        and "provider=openrouter" in record.getMessage()
        for record in caplog.records
    )
    assert not any(
        record.name == "app.ai.registry"
        and record.levelno == logging.WARNING
        for record in caplog.records
    )
    assert all("sk-test" not in record.getMessage() for record in caplog.records)
