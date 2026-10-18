from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest
import test_mission_a0
import test_mission_m01
import test_mission_m01_workflow as mission_workflow
import test_missions_a2
import test_postgres_sessions

from app.language_packs.loader import load_pack
from app.missions import get_mission
from app.repositories.postgres.workflow import _lesson_answer_is_correct, evaluate
from app.schemas.tasks import SubmitVocabularyReviewAttemptRequest
from app.services import mission_eligibility
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m01_a2_task
from app.services.mission_lessons_m01 import m01_lesson_task
from app.services.mission_registry import A2_MISSION_LESSONS

FIXTURE = Path(__file__).parent / "fixtures/m01_spanish_structure.json"
PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


@pytest.fixture
def database(monkeypatch):
    yield from test_postgres_sessions.database.__wrapped__(monkeypatch)


@pytest.fixture
def curated(database):
    yield from mission_workflow.curated.__wrapped__(database)


def _grading_scenarios(task):
    correct_answers = {}
    wrong_answers = {}
    for question in task.public_content.questions:
        question_id = question.question_id
        answer = task.answer_key.correct_option_ids.get(question_id)
        if answer is None:
            accepted = task.answer_key.accepted_text_answers_by_question.get(question_id, [])
            answer = accepted[0] if accepted else None
        if answer is None:
            raise AssertionError(f"No answer key for {question_id}")
        correct_answers[question_id] = answer
        if question.interaction_type == "multipleChoice":
            wrong_answers[question_id] = next(
                option.option_id for option in question.options if option.option_id != answer
            )
        else:
            wrong_answers[question_id] = "intentionally incorrect"

    scenarios = {}
    for name, answers in (
        ("all_correct", correct_answers),
        ("all_wrong", wrong_answers),
    ):
        request = SubmitVocabularyReviewAttemptRequest(answers=answers)
        question_results = {
            question.question_id: _lesson_answer_is_correct(
                task, question.question_id, answers[question.question_id]
            )
            for question in task.public_content.questions
        }
        scored_correct = evaluate(task, request)
        scenarios[name] = {
            "question_results": question_results,
            "score": int(scored_correct),
            "task_status_after_submission": "completed",
            "met_threshold": scored_correct,
        }
    return scenarios


def _structure(level, mission, result, task):
    public_content = task.public_content.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    evaluations = {
        item.question_id: item for item in task.answer_key.question_evaluations
    }
    questions = []
    for question in result.questions:
        evaluation = evaluations[question.question_id]
        correct_text = getattr(question, "correct_text", None)
        correct_option_id = getattr(question, "correct_option_id", None)
        correct_answer = correct_text
        if correct_answer is None and correct_option_id is not None:
            correct_answer = next(
                (
                    option.label
                    for option in question.options
                    if option.option_id == correct_option_id
                ),
                correct_option_id,
            )
        questions.append(
            {
                "purpose": question.purpose,
                "interaction_type": question.interaction_type,
                "section": question.section,
                "target_ids": evaluation.target_ids,
                "evidence_type": evaluation.evidence_type,
                "criteria": evaluation.rubric_criterion_ids,
                "correct_answer": correct_answer,
            }
        )
    section_counts = Counter(question["section"] for question in questions)
    interaction_counts = Counter(
        question["interaction_type"] for question in questions
    )
    return {
        "mission_id": mission.mission_id,
        "practice_level": str(mission.practice_level),
        "content_version": mission.content_version,
        "question_count": len(questions),
        "option_counts": [len(question.options) for question in result.questions],
        "public_content_keys": list(public_content),
        "support_shape": {
            key: len(value) if key == "prep" else value
            for key, value in public_content.items()
            if key in {"prep", "checkEachQuestion"}
        },
        "sections": list(section_counts),
        "section_counts": dict(section_counts),
        "interaction_counts": dict(interaction_counts),
        "questions": questions,
        "answer_key": task.answer_key.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "grading": _grading_scenarios(task),
    }


def current_structure(monkeypatch):
    counter = iter(range(1, 100))
    monkeypatch.setattr(test_mission_a0, "uuid4", lambda: UUID(int=next(counter)))
    mission, _spec, payload, a0_result, _objects = test_mission_a0._result("M01", "es")
    a0_task = a0_lesson_task(UUID(int=101), mission, payload, a0_result, {})
    a0 = _structure("A0", mission, a0_result, a0_task)

    a1_payload = test_mission_m01.build("es", session_id=UUID(int=202))
    a1_mission = test_mission_m01.MISSION
    a1_result = test_mission_m01.fallback_m01_lesson(a1_payload)
    a1_task = m01_lesson_task(UUID(int=202), a1_mission, a1_payload, a1_result, {})
    a1 = _structure("A1", a1_mission, a1_result, a1_task)

    objects, words, relations, groups, translated, markers = test_missions_a2._scene()
    a2_mission = get_mission("M01", "A2", 1)
    spec = A2_MISSION_LESSONS["A2:M01"]
    a2_payload = spec.payload(
        a2_mission,
        "es",
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "language-pack-regression",
        review_markers=markers,
    )
    a2_result = spec.generation.fallback(a2_payload)
    a2_task = m01_a2_task(UUID(int=303), a2_mission, a2_payload, a2_result, {})
    a2 = _structure("A2", a2_mission, a2_result, a2_task)
    return {"A0": a0, "A1": a1, "A2": a2}


def test_spanish_m01_structure_matches_current_builder_snapshot(monkeypatch):
    expected = json.loads(FIXTURE.read_text("utf-8"))

    assert current_structure(monkeypatch) == expected


def test_language_pack_package_is_absent_from_application_import_graph():
    code = (
        "import app.main, sys; "
        "assert not any(name == 'app.language_packs' or "
        "name.startswith('app.language_packs.') for name in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_existing_m01_grading_and_completion_path_remains_unchanged(curated, monkeypatch):
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (("M01", "A1", 1),))

    mission_workflow.test_submissions_grade_each_question_and_word_once(
        curated, "correct"
    )


def test_preview_pack_fixture_is_unreviewed():
    assert load_pack(PACK).provenance.review_status == "unreviewed"
