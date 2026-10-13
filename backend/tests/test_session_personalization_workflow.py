"""History changes the next lesson while preserving template and privacy boundaries."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, services
from test_preloaded_templates_workflow import curated as curated

from app.ai.cache import CacheScope
from app.main import create_app
from app.repositories.postgres.learner_history import snapshot_learner_history
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.base import utc_now
from app.schemas.sessions import ReviewPracticeRequest


def test_failed_grammar_generation_keeps_word_review_without_claiming_missing_focus(
    curated, monkeypatch,
):
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", "true")
    previous = _earlier_mixed_session(curated, monkeypatch)
    engine, _owner, profile, *_ = curated
    task_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(session_tasks).values(
            id=task_id, session_id=previous, phase="learning", kind="grammarLesson",
            order_index=100, status="completed", completed_at=utc_now(), public_content={
                "kind": "grammarLesson", "focus": "genderNumberAgreement",
                "questions": [{"question_id": "earlier-agreement"}],
            },
        ))
        connection.execute(insert(task_attempts).values(
            id=uuid4(), session_task_id=task_id, attempt_number=1, input_mode="multipleChoice",
            response_payload={"answers": {}}, is_correct=False,
            evaluation_details={"questionResults": {"earlier-agreement": False}},
        ))
    repository, records = _recorded_repository(curated, SceneModel(error=ValueError("offline")))
    sid, request = _prepare(curated, repository)
    repository.review(sid, profile.id, request)
    assert records["lessons"][0]["payload"]["learnerHistory"]["grammar"][
        "genderNumberAgreement"
    ]["lastOutcome"] == "incorrect"
    detail = repository.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    assert detail.personalization.returning_words
    assert detail.personalization.practice_focuses == []
    assert detail.translation_preview is not None
    assert not any(task.kind == "grammarLesson" for task in detail.tasks)


def _prepare(curated, repository, *, full_scene=True):
    _, _, profile, client, asset, _ = curated
    response = client.post("/api/v1/sessions", json={
        "languageProfileId": str(profile.id), "mediaAssetId": str(asset.id),
        "idempotencyKey": str(uuid4()),
    })
    assert response.status_code == 202, response.text
    sid = UUID(response.json()["session"]["id"])
    repository.analyze(sid, profile.id)
    detail = repository.get(sid, profile.id)
    request = ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in detail.scene_objects],
        object_attributes={obj.id: obj.attributes for obj in detail.scene_objects if obj.attributes}
        if full_scene else {},
        relations=detail.scene_object_relations if full_scene else [],
    )
    return sid, request


def _earlier_mixed_session(curated, monkeypatch, *, completed=True):
    """Persist real mixed question grading; source scene has no adjectives/relations."""
    engine, owner, profile, client, *_ = curated
    with monkeypatch.context() as setting:
        setting.setenv("LEARNER_MEMORY_ENABLED", "false")
        repository = PostgresWorkflowRepository(
            engine, owner.id, translator=services(SceneModel())["translation"],
        )
        sid, request = _prepare(curated, repository, full_scene=False)
        repository.review(sid, profile.id, request)
        detail = repository.get(sid, profile.id)
        introduction = next(task for task in detail.tasks if task.kind == "vocabularyIntroduction")
        weak_questions = {
            f"word-{word.learning_key}" for word in introduction.public_content.words
            if word.target_text == "la taza"
        }
        answers = {
            question.question_id: (
                next(option.option_id for option in question.options
                     if option.option_id != question.correct_option_id)
                if question.question_id in weak_questions else question.correct_option_id
            )
            for question in introduction.public_content.questions
        }
        response = client.post(f"/api/v1/tasks/{introduction.id}/attempts", json={
            "inputMode": "vocabularyReview", "answers": answers,
        })
        assert response.status_code == 200, response.text
        results = response.json()["attempt"]["evaluationDetails"]["questionResults"]
        assert set(results.values()) == {True, False}
        if completed:
            for task in detail.tasks:
                if task.id != introduction.id:
                    response = client.post(f"/api/v1/tasks/{task.id}/skip", json={
                        "reason": "Finished vocabulary practice",
                    })
                    assert response.status_code == 200, response.text
        action = "complete" if completed else "abandon"
        response = client.post(f"/api/v1/sessions/{sid}/{action}")
        assert response.status_code == 200, response.text
    return sid


def _recorded_repository(curated, model):
    engine, owner, *_ = curated
    features = services(model)
    records = {name: [] for name in features}

    def wrapper(name, method):
        def call(payload, **options):
            records[name].append({"payload": deepcopy(payload), "options": dict(options)})
            return getattr(features[name], method)(payload, **options)
        return SimpleNamespace(**{method: call})

    repository = PostgresWorkflowRepository(
        engine, owner.id,
        translator=wrapper("translation", "translate"),
        learning_task_generator=wrapper("lessons", "generate"),
        ispy_clue_generator=wrapper("clues", "generate"),
    )
    return repository, records


def _assert_private_grammar_only(records, owner, profile):
    grammar = records["lessons"][0]
    assert grammar["options"] == {
        "cache_scope": CacheScope.user(f"{owner.id}:{profile.id}"), "templates": None,
    }
    assert "learnerHistory" in grammar["payload"]
    for name in ("translation", "clues"):
        call = records[name][0]
        assert "learnerHistory" not in call["payload"]
        assert call["options"]["cache_scope"] == CacheScope.public()
        assert call["options"]["templates"] is not None
    assert records["translation"][0]["options"]["templates"] is (
        records["clues"][0]["options"]["templates"]
    )
    return grammar["payload"]["learnerHistory"]


def test_next_session_revisits_missed_words_and_keeps_saved_summary_private(curated, monkeypatch):
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", "true")
    _earlier_mixed_session(curated, monkeypatch)
    engine, owner, profile, client, *_ = curated
    model = SceneModel()
    repository, records = _recorded_repository(curated, model)
    sid, request = _prepare(curated, repository)
    repository.review(sid, profile.id, request)
    detail = repository.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    introduction = next(task for task in detail.tasks if task.kind == "vocabularyIntroduction")
    words = introduction.public_content.words
    assert words[0].target_text == "la taza"
    assert words[-1].target_text == "la mesa"
    assert {word.translation for word in words[1:-1]} == {"red", "on"}
    assert [question.question_id for question in introduction.public_content.questions] == [
        f"word-{word.learning_key}" for word in words
    ]
    history = _assert_private_grammar_only(records, owner, profile)
    observed = {word["term"]: word for word in history["words"]}
    assert observed["taza"]["lastOutcome"] == "incorrect"
    assert observed["mesa"]["lastOutcome"] == "correct"
    assert all(word["relevant"] for word in history["words"])
    assert history["totals"]["sessionsCompleted"] == 1
    assert model.requests == ["learning_tasks_v2"]
    assert len([task for task in detail.tasks if task.kind == "grammarLesson"]) == 4
    assert detail.personalization.previous_sessions == 1
    assert [word.needs_review for word in detail.personalization.returning_words] == [True, False]
    with engine.connect() as connection:
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == sid)
        ).scalar_one()
    assert "translationPreview" in draft and "personalization" in draft
    assert detail.translation_preview is not None
    encoded_draft = json.dumps(draft)
    assert "learnerHistory" not in encoded_draft
    assert "correctCount" not in encoded_draft and "journalMentions" not in encoded_draft
    with TestClient(create_app()) as restarted:
        response = restarted.get(f"/api/v1/sessions/{sid}")
        assert response.status_code == 200, response.text
        payload = response.json()
    assert payload["personalization"] == detail.personalization.model_dump(
        mode="json", by_alias=True,
    )
    assert payload["translationPreview"] == detail.translation_preview.model_dump(
        mode="json", by_alias=True,
    )
    assert "learnerHistory" not in response.text
    assert "correctCount" not in response.text and "journalMentions" not in response.text


@pytest.mark.parametrize("enabled,prior_history", [(True, False), (False, True)])
def test_empty_history_and_flag_off_preserve_curated_template_path(
    curated, monkeypatch, enabled, prior_history,
):
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", str(enabled).lower())
    if prior_history:
        _earlier_mixed_session(curated, monkeypatch)
    model = SceneModel(error=AssertionError("Curated provider must not be called"))
    repository, records = _recorded_repository(curated, model)
    sid, request = _prepare(curated, repository)
    repository.review(sid, curated[2].id, request)
    detail = repository.get(sid, curated[2].id)
    assert detail.session.status == "inProgress"
    assert detail.personalization is None
    assert model.requests == []
    for name in ("translation", "lessons", "clues"):
        call = records[name][0]
        assert "learnerHistory" not in call["payload"]
        assert call["options"]["cache_scope"] == CacheScope.public()
        assert call["options"]["templates"] is not None


def test_generation_uses_claimed_history_when_journal_evidence_arrives(curated, monkeypatch):
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", "true")
    _earlier_mixed_session(curated, monkeypatch)
    engine, owner, profile, client, *_ = curated
    repository, records = _recorded_repository(curated, SceneModel())
    sid, request = _prepare(curated, repository)
    repository._review(sid, profile.id, request)
    claim = repository._claim_generation(sid, profile.id)
    before = deepcopy(claim.learner_history)
    assert before["totals"]["sessionsCompleted"] == 1
    # Accepted writing arrives after the claim transaction is released, while
    # generation has not called its model. It must affect only later lessons.
    response = client.put("/api/v1/journal/today", json={
        "languageProfileId": str(profile.id), "content": "La taza.",
    })
    assert response.status_code == 200, response.text
    journal = response.json()
    response = client.post(f"/api/v1/journals/{journal['id']}/complete", json={
        "currentRevisionId": journal["currentRevisionId"],
    })
    assert response.status_code == 200, response.text
    with engine.connect() as connection:
        latest = snapshot_learner_history(
            connection, owner.id, profile.model_dump(by_alias=False), sid, [],
        )
    assert latest["totals"]["journalsCompleted"] == 1
    assert before["totals"]["journalsCompleted"] == 0
    repository._generate_tasks(claim)
    assert claim.learner_history == before
    sent = _assert_private_grammar_only(records, owner, profile)
    assert sent["totals"]["sessionsCompleted"] == 1
    assert sent["totals"]["journalsCompleted"] == 0
    assert {word["term"]: word["lastOutcome"] for word in sent["words"]} == {
        "taza": "incorrect", "mesa": "correct",
    }
    detail = repository.get(sid, profile.id)
    assert detail.session.status == "inProgress"
    assert detail.personalization.previous_sessions == 1


def test_accepted_practice_from_incomplete_session_still_personalizes(curated, monkeypatch):
    monkeypatch.setenv("LEARNER_MEMORY_ENABLED", "true")
    _earlier_mixed_session(curated, monkeypatch, completed=False)
    repository, records = _recorded_repository(curated, SceneModel())
    sid, request = _prepare(curated, repository)
    repository.review(sid, curated[2].id, request)
    detail = repository.get(sid, curated[2].id)
    assert detail.session.status == "inProgress"
    assert detail.personalization is not None
    assert detail.personalization.previous_sessions == 0
    introduction = next(task for task in detail.tasks if task.kind == "vocabularyIntroduction")
    assert introduction.public_content.words[0].target_text == "la taza"
    assert introduction.public_content.words[-1].target_text == "la mesa"
    history = _assert_private_grammar_only(records, curated[1], curated[2])
    assert history["totals"]["sessionsCompleted"] == 0
    assert history["totals"]["gradedAttempts"] == 1
