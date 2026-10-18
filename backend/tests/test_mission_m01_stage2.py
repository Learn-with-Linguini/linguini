"""Stage-two integration coverage for multilingual M01 generation."""

import json

import pytest
from sqlalchemy import select, update
from test_mission_m01_contract import planned_a1_output
from test_mission_m01_workflow import _answer_key, _lesson
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, TextModelResponse
from test_preloaded_templates_workflow import curated as curated

from app.api.dependencies import get_practice_repository
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.mission_m01_contract import (
    GeneratedMarkerOption,
    GeneratedQuestion,
    M01ContractInput,
    M01GeneratedLesson,
)
from app.schemas.tasks import TaskAnswerKey
from app.schemas.translation import SceneTranslationResult
from app.services import mission_eligibility


def generated_lesson(payload):
    contract = M01ContractInput.model_validate(payload["contract"])
    _, output, _ = planned_a1_output(contract)
    object_fact_ids = {item.fact_id for item in contract.scene_facts.objects}
    terms_by_fact = {}
    for term in contract.vocabulary:
        terms_by_fact.setdefault(term.fact_id, []).append(term.target_text)
    questions = []
    for question in output.questions:
        answer = output.private.answers[question.question_id]
        target_terms = [
            term
            for fact_id in question.fact_ids
            if fact_id in object_fact_ids
            for term in terms_by_fact.get(fact_id, [])
        ]
        options = question.options
        if answer.correct_option_id:
            options = [
                option.model_copy(update={
                    "label": " ".join([option.label, *target_terms]),
                })
                if option.option_id == answer.correct_option_id else option
                for option in question.options
            ]
        chunks = question.chunks
        if answer.chunk_ids and target_terms:
            first_answer_chunk = answer.chunk_ids[0]
            chunks = [
                chunk.model_copy(update={
                    "text": " ".join([chunk.text, *target_terms]),
                })
                if chunk.chunk_id == first_answer_chunk else chunk
                for chunk in question.chunks
            ]
        questions.append(GeneratedQuestion(
            question_id=question.question_id,
            target_ids=question.target_ids,
            section=question.section,
            prompt=question.prompt,
            prompt_translation=question.prompt_translation,
            instruction=question.instruction,
            interaction=question.interaction,
            options=options,
            marker_options=[
                GeneratedMarkerOption(option_id=option_id, fact_id=fact_id)
                for option_id, fact_id in (question.marker_fact_ids or {}).items()
            ],
            chunks=chunks,
            fact_ids=question.fact_ids,
            answer=answer,
            feedback=question.feedback,
        ))
    return M01GeneratedLesson(
        title=output.title,
        explanation=output.explanation,
        preparation=output.preparation,
        questions=questions,
    )


class MultilingualModel(SceneModel):
    def __init__(self, mode="valid", builder=generated_lesson):
        super().__init__()
        self.mode = mode
        self.builder = builder
        self.m01_calls = 0
        self.entered = None
        self.release = None
        self.payloads = []

    def generate(self, request, **options):
        if request.json_schema_name != "m01_multilingual_v1":
            return super().generate(request, **options)
        self.m01_calls += 1
        payload, _ = json.JSONDecoder().raw_decode(request.user_content)
        self.payloads.append(payload)
        if self.entered is not None and self.m01_calls > 2:
            self.entered.set()
            assert self.release is not None and self.release.wait(10)
        if self.mode == "invalid" or (self.mode == "repair" and self.m01_calls == 1):
            output = "{}"
        else:
            body = self.builder(payload)
            output = json.dumps(body.model_dump(mode="json", by_alias=True), ensure_ascii=False)
        return TextModelResponse(
            output_text=output,
            model_name="test-text-model",
            prompt_version=request.prompt_version,
            input_tokens=10,
            output_tokens=10,
        )


def enable_m01(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "*")
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (("M01", "A1", 1),))


def use_repository(client, repository):
    client.app.dependency_overrides[get_practice_repository] = lambda: repository


def make_ko(curated):
    engine, _, profile, *_ = curated
    with engine.begin() as connection:
        connection.execute(
            update(language_profiles)
            .where(language_profiles.c.id == profile.id)
            .values(target_language_code="ko")
        )


def test_saved_legacy_m01_task_loads_and_grades_after_enabling_generation(
    curated, monkeypatch
):
    monkeypatch.setitem(
        mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (("M01", "A1", 1),)
    )
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "false")
    monkeypatch.delenv("MULTILINGUAL_COMBINATIONS", raising=False)
    engine, _, profile, client, *_ = curated
    repository, session_id, detail = _lesson(curated, SceneModel())
    legacy = next(
        task for task in detail.tasks if task.public_content.mission_id == "M01"
    )
    saved_content = legacy.public_content

    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "*")
    refreshed = repository.get(session_id, profile.id)
    loaded = next(
        task for task in refreshed.tasks if task.public_content.mission_id == "M01"
    )
    assert loaded.id == legacy.id
    assert loaded.public_content == saved_content

    use_repository(client, repository)
    answers = _answer_key(engine, legacy.id)["correctOptionIds"]
    response = client.post(f"/api/v1/tasks/{legacy.id}/attempts", json={
        "inputMode": "vocabularyReview",
        "answers": answers,
        "idempotencyKey": f"legacy-{legacy.id}",
    })
    assert response.status_code == 200, response.text
    assert response.json()["attempt"]["isCorrect"] is True


def test_multilingual_repair_succeeds_and_saves_task(curated, monkeypatch):
    enable_m01(monkeypatch)
    model = MultilingualModel("repair")
    repository, session_id, detail = _lesson(curated, model)
    tasks = [task for task in detail.tasks if task.public_content.mission_id == "M01"]
    assert model.m01_calls == 2
    assert len(tasks) == 1
    assert tasks[0].kind == "grammarLesson"
    answer_key = TaskAnswerKey.model_validate(_answer_key(repository.engine, tasks[0].id))
    assert all(
        item.evidence_type != "production"
        for item in answer_key.question_evaluations
    )
    with repository.engine.connect() as connection:
        saved = connection.execute(
            select(session_tasks.c.id).where(
                session_tasks.c.session_id == session_id,
                session_tasks.c.id == tasks[0].id,
            )
        ).scalar_one_or_none()
    assert saved == tasks[0].id


def test_m01_input_includes_spanish_reviewed_examples(curated, monkeypatch):
    enable_m01(monkeypatch)
    model = MultilingualModel()
    _lesson(curated, model)

    assert model.payloads[0]["contract"]["reviewedExamples"] == [
        "una mesa",
        "un libro",
        "Es una mesa blanca.",
        "Es un libro rojo.",
        "Está al lado de la puerta.",
    ]


def test_m01_learner_context_uses_progress_and_history_snapshot_shapes(
    curated, monkeypatch
):
    enable_m01(monkeypatch)
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", "true")
    progress = {
        "objects": {f"word-{index}": 0.5 for index in range(10)},
        "terms": {f"term-{index}": 0.75 for index in range(5)},
        "plurals_taught": True,
        "term_familiarity": {"ignored-snake": 0.1},
        "termFamiliarity": {"ignored-camel": 0.2},
        "familiarity": {"ignored": 0.3},
        "recent_mission_ids": ["M02"],
        "recentMissionIds": ["M03"],
    }
    history = {
        "version": 1,
        "profile": {
            "sourceLanguage": "en",
            "targetLanguage": "es",
            "proficiencyLevel": "A1",
        },
        "totals": {
            "sessionsCompleted": 1,
            "gradedAttempts": 4,
            "readingTasksCompleted": 0,
            "journalsCompleted": 0,
        },
        "words": [
            {
                "term": f"history-{index}",
                "source": f"source-{index}",
                "seenCount": 1,
                "correctCount": 3,
                "incorrectCount": 1,
                "lastOutcome": "correct",
                "journalMentions": 0,
                "assistedJournalMentions": 0,
                "journalSelections": 0,
                "relevant": True,
            }
            for index in range(10)
        ],
        "grammar": {},
        "journal": {"acceptedCorrections": {}},
    }
    monkeypatch.setattr(
        PostgresWorkflowRepository,
        "_mission_progress",
        lambda self, connection, profile, learner_history: progress,
    )
    monkeypatch.setattr(
        "app.repositories.postgres.workflow.snapshot_learner_history",
        lambda *args: history,
    )
    model = MultilingualModel()
    _lesson(curated, model)

    learner = model.payloads[0]["contract"]["learner"]
    familiarity = learner["termFamiliarity"]
    assert len(familiarity) == 20
    assert familiarity["object:word-0"] == 0.5
    assert familiarity["term:term-0"] == 0.75
    assert familiarity["history:history-0"] == 0.75
    assert learner["recentMissionIds"] == []
    assert learner["pluralsTaught"] is True


def test_translation_vocabulary_write_merges_the_current_draft(curated):
    repository, session_id, detail = _lesson(curated)
    stale_session = detail.session
    latest_draft = {
        **(stale_session.analysis_draft or {}),
        "missionChecks": {"task": {"question": {"isCorrect": True}}},
        "skippedMissions": [{"missionId": "M02", "reason": "noReviewedContent"}],
    }
    with repository.engine.begin() as connection:
        connection.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(analysis_draft=latest_draft)
        )
    translated_scene = SceneTranslationResult.model_validate(
        stale_session.analysis_draft["translationPreview"]
    )

    with repository.transaction() as connection:
        repository._store_translation(
            connection,
            stale_session,
            curated[2].model_dump(by_alias=False),
            detail.scene_objects,
            translated_scene,
        )

    current_draft = repository.get(session_id).session.analysis_draft
    assert current_draft["missionChecks"] == latest_draft["missionChecks"]
    assert current_draft["skippedMissions"] == latest_draft["skippedMissions"]
    assert current_draft["m01SupplementalVocabulary"]


@pytest.mark.parametrize(
    ("language", "expected_task", "expected_skip"),
    [
        ("es", True, None),
        ("ko", False, "generationFailed"),
    ],
)
def test_repair_exhaustion_uses_only_allowed_fallback(
    curated, monkeypatch, language, expected_task, expected_skip
):
    enable_m01(monkeypatch)
    if language == "ko":
        make_ko(curated)
    model = MultilingualModel("invalid")
    _, _, detail = _lesson(curated, model)
    m01_tasks = [task for task in detail.tasks if task.public_content.mission_id == "M01"]
    skipped = next(
        (item for item in detail.session.analysis_draft.get("skippedMissions", [])
         if item["missionId"] == "M01"),
        None,
    )
    assert model.m01_calls == 2
    assert bool(m01_tasks) is expected_task
    if expected_skip:
        assert skipped == {
            "missionId": "M01",
            "reason": expected_skip,
        }
    else:
        assert skipped is None
        assert m01_tasks[0].public_content.mission_id == "M01"
