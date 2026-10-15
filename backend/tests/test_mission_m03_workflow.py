"""M03 A1 lessons on a confirmed scene: counts, planning, grading, resuming and completion."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from test_mission_m01_workflow import (
    _analyzed,
    _answer_key,
    _attempt,
    _repository,
    _review,
    _scalar,
)
from test_mission_m02_workflow import (
    _planned,
    _without_clue_model,
)
from test_postgres_sessions import database as database
from test_preloaded_templates import SceneModel, TextModelResponse
from test_preloaded_templates_workflow import curated as curated

from app.ai.features.learning_tasks import service as learning_service
from app.ai.features.learning_tasks.mission_m03 import (
    M03_PROMPT_VERSION,
    M03_SCHEMA_VERSION,
    fallback_m03_lesson,
)
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import task_attempts
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.sessions import AddedPracticeObject, ReviewPracticeRequest
from app.schemas.tasks import SkipTaskRequest
from app.services import mission_lessons_m03


class M03Model(SceneModel):
    """Answers the M03 lesson request with valid content of its own."""

    def generate(self, request, **options):
        if request.json_schema_name != "mission_lesson_m03_v1":
            return super().generate(request, **options)
        self.requests.append(request.json_schema_name)
        result = fallback_m03_lesson(json.loads(request.user_content))
        body = result.model_copy(update={"title": "Model lesson"}).model_dump(
            mode="json", by_alias=True
        )
        return TextModelResponse(
            output_text=json.dumps(body), model_name="test-text-model",
            prompt_version=request.prompt_version, input_tokens=10, output_tokens=10,
        )


def _cup(detail):
    return next(obj for obj in detail.scene_objects if obj.label == "cup")


def _counts_only(quantity=3):
    def review(detail):
        return ReviewPracticeRequest(
            accepted_object_ids=[obj.id for obj in detail.scene_objects],
            object_counts={_cup(detail).id: quantity},
        )
    return review


def _everything(detail):
    return _review(detail).model_copy(update={"object_counts": {_cup(detail).id: 3}})


def _suggest(engine, sid, value):
    """Have the scene analysis report a quantity for the cup."""
    draft = _draft(engine, sid)
    for item in draft["objects"]:
        if item["label"] == "cup":
            item["attributes"] = {**(item.get("attributes") or {}), "quantity": value}
    with engine.begin() as connection:
        connection.execute(update(sessions).where(sessions.c.id == sid).values(
            analysis_draft=draft,
        ))


def _lesson(curated, review, model=None, suggestion=None):
    engine, profile = curated[0], curated[2]
    model = model or SceneModel()
    # The scripted clue model needs a colour and a relation; partial scenes use fallbacks.
    repository = (
        _repository(curated, model) if review is _everything
        else _without_clue_model(curated, model)
    )
    sid, analyzed = _analyzed(curated, repository)
    if suggestion is not None:
        _suggest(engine, sid, suggestion)
        analyzed = repository.get(sid, profile.id)
    repository.review(sid, profile.id, review(analyzed))
    return repository, sid, repository.get(sid, profile.id)


def _draft(engine, sid):
    return _scalar(engine, select(sessions.c.analysis_draft).where(sessions.c.id == sid))


def _m03(detail):
    return next(task for task in detail.tasks if task.public_content.mission_id == "M03")


@pytest.mark.parametrize(("suggestion", "quantity", "source"), [
    ("3", 3, "confirmed"), ("two", 3, "corrected"), (None, 3, "entered"),
])
def test_the_learners_count_is_saved_with_its_group(
    curated, suggestion, quantity, source,
):
    engine = curated[0]
    _repository_, sid, detail = _lesson(curated, _counts_only(quantity), suggestion=suggestion)
    (group,) = _draft(engine, sid)["countedGroups"]
    assert group == {
        "sceneObjectIds": [str(_cup(detail).id)], "label": "cup", "quantity": quantity,
        "suggestedQuantity": None if suggestion is None else {"3": 3, "two": 2}[suggestion],
        "source": source,
    }
    assert [item.quantity for item in detail.counted_groups] == [quantity]


def test_a_photo_with_only_a_count_plans_m03(curated):
    engine, _owner, _profile, client, *_ = curated
    model = SceneModel()
    _repository_, sid, detail = _lesson(curated, _counts_only(), model)
    assert _planned(detail) == ["M03"]
    introduction, lesson, *bonus = detail.tasks
    assert introduction.kind == "vocabularyIntroduction"
    assert bonus and {task.kind for task in bonus} <= {"ispyRound", "reflection"}
    assert "mission_lesson_m03_v1" in model.requests
    assert lesson.public_content.title == "Say how many"
    assert lesson.public_content.explanation is None
    questions = lesson.public_content.questions
    assert [q.interaction_type for q in questions] == [
        "multipleChoice", "multipleChoice", "sentenceBuilding",
    ]
    key = _answer_key(engine, lesson.id)
    assert key["correctOptionIds"][questions[-1].question_id] == "Hay tres tazas."
    assert [item["targetIds"] for item in key["questionEvaluations"]] == [
        ["understand-quantity"], ["say-quantity", "plural-noun"], ["say-quantity", "plural-noun"],
    ]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public
    assert _draft(engine, sid)["missionPlan"] == [
        {"missionId": "M03", "practiceLevel": "A1", "contentVersion": 1}
    ]


@pytest.mark.parametrize("quantity", [None, 1])
def test_a_missing_or_single_count_does_not_qualify(curated, quantity):
    profile = curated[2]
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    request = ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in analyzed.scene_objects],
        object_counts={} if quantity is None else {_cup(analyzed).id: quantity},
    )
    repository.review(sid, profile.id, request)
    detail = repository.get(sid, profile.id)
    tips = " ".join(detail.mission_guidance)
    assert "Say how many: Count a group of 2 to 10 matching objects." in tips
    assert all(task.public_content.mission_key is None for task in detail.tasks)


def test_a_group_of_matching_objects_is_counted_once(curated):
    profile = curated[2]
    repository = _repository(curated, SceneModel())
    sid, analyzed = _analyzed(curated, repository)
    extra = AddedPracticeObject(id=uuid4(), label="Cup", x=0.5, y=0.5)
    request = ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in analyzed.scene_objects],
        added_objects=[extra],
        object_counts={_cup(analyzed).id: 3, extra.id: 2},
    )
    with pytest.raises(PracticeConflictError, match="Count each group"):
        repository.review(sid, profile.id, request)


def test_valid_m03_model_lesson_uses_its_own_cache_identity(curated, monkeypatch):
    versions = []
    original = learning_service.run_cached

    def recording(*args, **kwargs):
        versions.append(kwargs["version"])
        return original(*args, **kwargs)

    monkeypatch.setattr(learning_service, "run_cached", recording)
    _repository_, _sid, detail = _lesson(curated, _counts_only(), M03Model())
    assert _m03(detail).public_content.title == "Model lesson"
    assert [(v.prompt_version, v.schema_version) for v in versions] == [
        (f"{M03_PROMPT_VERSION}:M03-A1.v1", M03_SCHEMA_VERSION)
    ]


@pytest.mark.parametrize("scenario", ["correct", "partial", "incorrect"])
def test_m03_submissions_grade_each_question_once(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated, _counts_only())
    lesson = _m03(detail)
    understand, choose, build = lesson.public_content.questions
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    singular = next(o.option_id for o in choose.options if o.label == "Hay tres taza.")
    wrong_meaning = next(
        o.option_id for o in understand.options if o.option_id != correct[understand.question_id]
    )
    answers = {
        "correct": correct,
        "partial": {**correct, build.question_id: "Hay cuatro tazas."},
        "incorrect": {understand.question_id: wrong_meaning, choose.question_id: singular,
                      build.question_id: "Hay tres taza."},
    }[scenario]
    first = _attempt(client, lesson, answers, key="m03-answer")
    assert first.status_code == 200, first.text
    xp = select(func.count()).select_from(xp_events).where(xp_events.c.session_id == sid)
    awarded = _scalar(engine, xp)
    repeat = _attempt(client, lesson, answers, key="m03-answer")
    assert repeat.json()["attempt"]["id"] == first.json()["attempt"]["id"]
    assert _scalar(engine, xp) == awarded
    assert _scalar(engine, select(func.count()).select_from(task_attempts).where(
        task_attempts.c.session_task_id == lesson.id
    )) == 1
    details = first.json()["attempt"]["evaluationDetails"]
    assert details["questionResults"] == {qid: answers[qid] == correct[qid] for qid in correct}
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    assert outcomes[build.question_id]["evidenceType"] == "construction"
    assert outcomes[build.question_id]["assistance"] == ["wordBank"]
    mistakes = {
        qid: [item["mistake"] for item in outcome["mistakes"]]
        for qid, outcome in outcomes.items()
    }
    expected = {
        "correct": {understand.question_id: [], choose.question_id: [], build.question_id: []},
        "partial": {understand.question_id: [], choose.question_id: [],
                    build.question_id: ["wrongQuantity"]},
        "incorrect": {understand.question_id: ["wrongQuantity"],
                      choose.question_id: ["pluralForm"], build.question_id: ["pluralForm"]},
    }[scenario]
    assert mistakes == expected


def test_a_photo_fitting_all_three_plans_all_three(curated):
    engine, _owner, profile, *_ = curated
    repository, sid, detail = _lesson(curated, _everything)
    assert _planned(detail) == ["M01", "M02", "M03"]
    kinds = [task.kind for task in detail.tasks]
    assert kinds[:4] == ["vocabularyIntroduction", *["grammarLesson"] * 3]
    assert "ispyRound" in kinds[4:]
    resumed = repository.get(sid, profile.id)
    assert [task.id for task in resumed.tasks] == [task.id for task in detail.tasks]
    assert [m.mission_id for m in repository._planned_missions(
        resumed.session.model_copy(update={"analysis_draft": _draft(engine, sid)}),
        {"proficiency_level": "A1", "target_language_code": "es"},
    )] == ["M01", "M02", "M03"]
    for task in detail.tasks[:4]:
        repository.task_action(task.id, "skip", SkipTaskRequest())
    with pytest.raises(PracticeConflictError):
        repository.finish(sid, profile.id)
    for task in detail.tasks[4:]:
        repository.task_action(task.id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"


def test_a_noun_without_a_reviewed_plural_skips_m03_for_the_regular_lesson(
    curated, monkeypatch,
):
    engine = curated[0]
    monkeypatch.setattr(mission_lessons_m03, "regular_plural", lambda *_: None)
    _repository_, sid, detail = _lesson(curated, _counts_only())
    assert _planned(detail) == []
    assert _draft(engine, sid)["skippedMissions"] == [
        {"missionId": "M03", "reason": "noReviewedContent"}
    ]
    assert detail.session.status == "inProgress"
    assert detail.tasks[0].kind == "vocabularyIntroduction"
    assert "grammarExplanation" in {task.kind for task in detail.tasks}
