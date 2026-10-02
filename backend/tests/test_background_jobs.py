"""The AI round-trips run behind the background-runner seam, not on the request path."""

from types import SimpleNamespace
from uuid import UUID

from test_postgres_sessions import create_run, vocabulary_answer
from test_postgres_sessions import database as database

from app.ai.features.translation.schemas import SceneTranslationResult
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.sessions import ReviewPracticeRequest
from app.services.session_plan import build_tasks


class DeferringRunner:
    """Records submitted jobs instead of running them, so tests control timing."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, /, *args, **kwargs):
        self.jobs.append(lambda: fn(*args, **kwargs))


def test_translations_are_committed_before_lesson_generation(database):
    engine, owner, profile, client = database
    runner = DeferringRunner()
    observed = []
    attempts = []
    completions = []

    def translate(payload):
        return SceneTranslationResult.model_validate({
            kind: [
                {**term, "translation": "mesa", "phoneticText": "MEH-sah"}
                for term in payload[kind]
            ]
            for kind in ("objects", "attributes", "relationships")
        })

    def generate(_payload):
        # A separate reader must see the checkpoint before this slow call ends.
        observed.append(repo.get(sid, profile.id))
        intro = observed[-1].tasks[0]
        # Exercise the public API during generation; this would block if the
        # generation call still held the user's database lock.
        attempts.append(client.post(
            f"/api/v1/tasks/{intro.id}/attempts",
            json=vocabulary_answer(intro.public_content.model_dump(mode="json"))
            | {"idempotencyKey": "early-vocabulary-test"},
        ))
        completions.append(client.post(f"/api/v1/sessions/{sid}/complete"))
        raise ValueError("Use deterministic tasks for this test")

    repo = PostgresWorkflowRepository(
        engine, owner.id, background=runner,
        translator=SimpleNamespace(translate=translate),
        learning_task_generator=SimpleNamespace(generate=generate),
    )
    sid = UUID(create_run(client, profile)["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    repo.review(sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id]))
    runner.jobs.pop()()
    assert len(observed) == 1
    assert observed[0].session.status == "generatingTasks"
    assert observed[0].translation_preview.objects[0].translation == "mesa"
    assert len(observed[0].tasks) == 1
    assert observed[0].tasks[0].kind == "vocabularyIntroduction"
    assert attempts[0].status_code == 200, attempts[0].text
    assert completions[0].status_code == 409
    settled = repo.get(sid, profile.id)
    assert settled.session.status == "inProgress"
    assert settled.tasks
    assert settled.vocabulary[0].phonetic_text == "MEH-sah"
    intro = next(task for task in settled.tasks if task.kind == "vocabularyIntroduction")
    assert intro.id == observed[0].tasks[0].id
    assert intro.status == "completed"
    assert intro.public_content.words[0].phonetic_text == "MEH-sah"


def test_preloaded_analysis_is_ready_without_a_background_job(database):
    engine, owner, profile, client = database
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(engine, owner.id, background=runner)
    sid = UUID(create_run(client, profile)["session"]["id"])
    detail = repo.analyze(sid, profile.id)
    assert detail.session.status == "awaitingObjectReview"
    assert not runner.jobs
    settled = repo.get(sid, profile.id)
    assert settled.session.status == "awaitingObjectReview"
    assert settled.scene_objects


def test_analyzer_failure_fails_the_session_without_escaping(database):
    engine, owner, profile, client = database
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(
        engine,
        owner.id,
        analyzer=SimpleNamespace(analyze=lambda *args: 1 / 0),
        background=runner,
    )
    sid = UUID(create_run(client, profile)["session"]["id"])
    assert repo.analyze(sid, profile.id).session.status == "failed"
    session = repo.get(sid, profile.id).session
    assert session.status == "failed"
    assert session.failure_code == "sceneAnalysisFailed"


def test_moderation_rejection_fails_the_session_with_moderation_code(database):
    from app.ai.features.scene_analysis import (
        SceneAnalysisModelError,
        SceneAnalysisModelErrorCode,
    )

    engine, owner, profile, client = database
    runner = DeferringRunner()

    def analyze(*args):
        raise SceneAnalysisModelError(
            SceneAnalysisModelErrorCode.IMAGE_REJECTED,
            "scene image was rejected by moderation",
        )

    repo = PostgresWorkflowRepository(
        engine,
        owner.id,
        analyzer=SimpleNamespace(analyze=analyze),
        background=runner,
    )
    sid = UUID(create_run(client, profile)["session"]["id"])
    # Preloaded scenes use their saved analysis on the request path, so a
    # rejection is persisted before analyze() returns.
    assert repo.analyze(sid, profile.id).session.status == "failed"
    assert not runner.jobs
    detail = repo.get(sid, profile.id)
    assert detail.session.status == "failed"
    assert detail.session.failure_code == "imageModerationFailed"
    assert not detail.scene_objects


def test_review_claims_then_defers_task_generation(database):
    engine, owner, profile, client = database
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(engine, owner.id, background=runner)
    sid = UUID(create_run(client, profile)["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    detail = repo.review(
        sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id])
    )
    assert detail.session.status == "generatingTasks"
    assert not detail.tasks
    assert len(runner.jobs) == 1
    runner.jobs.pop()()
    settled = repo.get(sid, profile.id)
    assert settled.session.status == "inProgress"
    assert settled.tasks


def test_task_generation_failure_fails_the_session_without_escaping(database):
    engine, owner, profile, client = database
    runner = DeferringRunner()
    repo = PostgresWorkflowRepository(
        engine,
        owner.id,
        translator=SimpleNamespace(translate=lambda *args: 1 / 0),
        background=runner,
    )
    sid = UUID(create_run(client, profile)["session"]["id"])
    repo.analyze(sid, profile.id)
    objects = repo.get(sid, profile.id).scene_objects
    detail = repo.review(
        sid, profile.id, ReviewPracticeRequest(accepted_object_ids=[objects[0].id])
    )
    assert detail.session.status == "generatingTasks"
    runner.jobs.pop()()
    session = repo.get(sid, profile.id).session
    assert session.status == "failed"
    assert session.failure_code == "taskGenerationFailed"


def test_vocabulary_introduction_questions_always_carry_the_answer():
    """Clients grade vocabulary taps locally, so every question needs its answer."""
    from app.schemas.media import SceneObject
    from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation

    session_id = UUID(int=1)
    words = [
        VocabularyItem(
            language_code="es", lemma=text, display_text=text, part_of_speech="noun"
        )
        for text in ["silla", "mesa"]
    ]
    objects = [
        SceneObject(session_id=session_id, label=label, vocabulary_item_id=word.id)
        for word, label in zip(words, ["chair", "table"], strict=True)
    ]
    translations = [
        VocabularyTranslation(
            vocabulary_item_id=word.id, source_language_code="en", translated_text=label
        )
        for word, label in zip(words, ["chair", "table"], strict=True)
    ]
    tasks = build_tasks(session_id, objects, words, translations, uploaded=False)
    introductions = [task for task in tasks if task.kind == "vocabularyIntroduction"]
    assert len(introductions) == 1
    questions = introductions[0].public_content.questions
    assert questions
    for question in questions:
        assert question.correct_option_id
    for question in introductions[0].public_content.model_dump(mode="json")["questions"]:
        assert question["correctOptionId"]
