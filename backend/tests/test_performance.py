"""Performance guards: one shared AI runtime, lean polling and overlapping model calls."""

import logging
import threading
import time
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import event
from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

import app.ai.registry as registry
from app.ai import NoOpAITracer, load_ai_settings
from app.ai.contracts.text import TextModelRequest, TextModelResponse
from app.ai.features.ispy_clues import ISpyClueGenerationError
from app.ai.features.translation.schemas import SceneTranslationResult
from app.ai.runtime import AiRuntime
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.ispy_clues import ISpyClueResult
from app.schemas.learning_tasks import LearningTaskResult
from app.schemas.sessions import ReviewPracticeRequest
from app.services.background import ThreadPoolBackgroundRunner
from tests.test_learning_task_service import tasks as learning_tasks

CONFIGURED = {
    "AI_OPENAI_API_KEY": "sk-test",
    "AI_GEMINI_API_KEY": "gemini-test",
    "AI_OPENROUTER_API_KEY": "openrouter-test",
}
MODEL_SECONDS = 0.4
CLUE = "es roja y está a la izquierda"


@pytest.fixture
def built(monkeypatch):
    """Provider clients constructed while the test runs."""
    calls = []
    for name in ("build_text_client", "build_vision_client"):
        original = getattr(registry, name)

        def counting(provider, *args, _original=original, **kwargs):
            calls.append(provider)
            return _original(provider, *args, **kwargs)

        monkeypatch.setattr(registry, name, counting)
    return calls


class SlowModels:
    """Fake providers that take ``MODEL_SECONDS`` and record when each call ran."""

    def __init__(self, lesson_error=None, clue_error=None):
        self.spans = {}
        self.lesson_error = lesson_error
        self.clue_error = clue_error
        self.translator = SimpleNamespace(translate=self.translate)
        self.learning_task_generator = SimpleNamespace(generate=self.lessons)
        self.ispy_clue_generator = SimpleNamespace(generate=self.clues)

    def _run(self, name, error, result):
        started = time.perf_counter()
        time.sleep(MODEL_SECONDS)
        self.spans[name] = (started, time.perf_counter())
        if error:
            raise error
        return result

    def translate(self, payload, cache_scope=None):
        return SceneTranslationResult.model_validate({
            kind: [{**term, "translation": "mesa"} for term in payload[kind]]
            for kind in ("objects", "attributes", "relationships")
        })

    def lessons(self, _payload, cache_scope=None):
        return self._run(
            "lessons", self.lesson_error, LearningTaskResult.model_validate(learning_tasks())
        )

    def clues(self, payload, cache_scope=None):
        key = payload["objects"][0]["key"]
        return self._run("clues", self.clue_error, ISpyClueResult.model_validate({"clues": [{
            "clue": CLUE, "answerObjectKey": key, "objectKeys": [key], "relationshipKeys": [],
        }]}))

    def overlapped(self):
        (lesson_start, lesson_end), (clue_start, clue_end) = (
            self.spans["lessons"], self.spans["clues"]
        )
        return lesson_start < clue_end and clue_start < lesson_end


def repository(database, models, **kwargs):
    engine, owner, _profile, _client = database
    return PostgresWorkflowRepository(
        engine,
        owner.id,
        translator=models.translator,
        learning_task_generator=models.learning_task_generator,
        ispy_clue_generator=models.ispy_clue_generator,
        **kwargs,
    )


def review(database, repo):
    _engine, _owner, profile, client = database
    sid = UUID(create_run(client, profile)["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    repo.review(sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id]))
    return sid


class _FakeProviderClient:
    def __init__(self, _key, _config, **_options):
        pass

    def generate(self, request, **_options):
        return TextModelResponse(
            output_text="{}", model_name="m", prompt_version=request.prompt_version
        )


_REQUEST = TextModelRequest(
    system_prompt="s",
    user_content="u",
    json_schema_name="n",
    json_schema={},
    prompt_version="v",
)


def test_runtime_builds_each_provider_client_once(built, monkeypatch):
    monkeypatch.setattr(registry, "OpenRouterTextClient", _FakeProviderClient)
    runtime = AiRuntime(load_ai_settings(CONFIGURED), NoOpAITracer())
    threads = [threading.Thread(target=runtime.translator) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert runtime.translator() is runtime.translator()
    assert runtime.ispy_guess_generator() is runtime.ispy_guess_generator()
    assert built == []

    threads = [
        threading.Thread(target=service._client.generate, args=(_REQUEST,))
        for service in (runtime.translator(), runtime.ispy_guess_generator())
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(built) == 2


def test_session_polling_reuses_the_runtime_and_builds_no_clients(database, built):
    _engine, _owner, profile, client = database
    client.app.state.ai_settings = load_ai_settings(CONFIGURED)
    sid = create_run(client, profile)["session"]["id"]
    runtime = client.app.state.ai_runtime
    queries = []

    def count(*_args):
        queries[-1] += 1

    app_engine = client.app.state.database_engine.engine
    event.listen(app_engine, "before_cursor_execute", count)
    try:
        for path in [f"/api/v1/sessions/{sid}"] * 3 + ["/api/v1/sessions/active"]:
            queries.append(0)
            assert client.get(path).status_code == 200
    finally:
        event.remove(app_engine, "before_cursor_execute", count)

    assert built == []
    assert client.app.state.ai_runtime is runtime
    assert runtime._services == {}
    # User, profile, session, media asset, curated scene, scene objects, tasks;
    # `active` also confirms the user exists before reading.
    assert queries == [7, 7, 7, 8]


def test_lessons_and_clues_overlap_after_translation(database):
    models = SlowModels()
    repo = repository(database, models)
    started = time.perf_counter()
    sid = review(database, repo)
    elapsed = time.perf_counter() - started

    assert models.overlapped()
    assert elapsed < 2 * MODEL_SECONDS
    detail = repo.get(sid, database[2].id)
    assert detail.session.status == "inProgress"
    kinds = [task.kind for task in detail.tasks]
    assert kinds.count("grammarLesson") == 4
    clues = [task for task in detail.tasks if task.kind == "ispyRound"]
    assert [task.public_content.clue for task in clues] == [CLUE]


@pytest.mark.parametrize(
    ("lesson_error", "clue_error"),
    [(ValueError("lessons down"), None), (None, ISpyClueGenerationError("clues down"))],
)
def test_one_failed_generation_keeps_the_other_result(database, lesson_error, clue_error):
    models = SlowModels(lesson_error=lesson_error, clue_error=clue_error)
    repo = repository(database, models)
    sid = review(database, repo)

    assert models.overlapped()
    detail = repo.get(sid, database[2].id)
    assert detail.session.status == "inProgress"
    grammar = [task for task in detail.tasks if task.kind == "grammarLesson"]
    clues = [task.public_content.clue for task in detail.tasks if task.kind == "ispyRound"]
    assert clues
    if lesson_error:
        assert not grammar
        assert clues == [CLUE]
    else:
        assert len(grammar) == 4
        assert CLUE not in clues


def test_generation_finishes_on_a_single_worker_background_pool(database):
    models = SlowModels()
    runner = ThreadPoolBackgroundRunner(max_workers=1)
    repo = repository(database, models, background=runner)
    try:
        sid = review(database, repo)
        deadline = time.monotonic() + 10
        while repo.get(sid, database[2].id).session.status != "inProgress":
            assert time.monotonic() < deadline, "task generation did not finish"
            time.sleep(0.05)
    finally:
        runner.shutdown(wait=True)

    assert models.overlapped()


def test_generation_logs_stage_and_transaction_timings(database, caplog):
    caplog.set_level(logging.DEBUG, logger="app.repositories.postgres.workflow")
    review(database, repository(database, SlowModels()))

    messages = [record.getMessage() for record in caplog.records]
    for stage in ("translation", "learning-task generation", "I-Spy clue generation"):
        assert any(message.startswith(f"Task generation {stage} took") for message in messages)
    assert any(
        message.startswith("Workflow transaction held the user lock for")
        for message in messages
    )
