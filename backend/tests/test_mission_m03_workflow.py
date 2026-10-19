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
from test_preloaded_templates import SceneModel
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import PostgresTaskRepository, task_attempts
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError
from app.schemas.sessions import AddedPracticeObject, ReviewPracticeRequest
from app.schemas.tasks import SessionTask, SkipTaskRequest
from app.services import mission_eligibility, mission_lessons_m03


@pytest.fixture(autouse=True)
def existing_a1_missions(monkeypatch):
    """Keep legacy mission workflows independent of the newly added M04/M05 variants."""
    monkeypatch.setitem(
        mission_eligibility.IMPLEMENTED_MISSIONS,
        "A1",
        (("M01", "A1", 1), ("M02", "A1", 2), ("M03", "A1", 1)),
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
    introduction, lesson = detail.tasks
    assert introduction.kind == "vocabularyIntroduction"
    # M03 is deterministic: the lesson model is never asked.
    assert not any(name.startswith("mission_lesson_m03") for name in model.requests)
    assert lesson.public_content.title == "Say how many"
    assert lesson.public_content.explanation is None
    questions = lesson.public_content.questions
    assert [q.question_id for q in questions] == [
        "choose-quantity", "build-quantity", "match-quantity",
    ]
    assert [q.interaction_type for q in questions] == [
        "multipleChoice", "sentenceBuilding", "multipleChoice",
    ]
    choose, build, match = questions
    assert choose.prompt == "¿Cuántas tazas hay?"
    assert choose.section == "Task 1 · Count in your photo"
    assert choose.group_object_ids == [_cup(detail).id]
    assert match.section == "Task 2 · Practice board"
    assert match.board_object_id is not None and match.quantity_word
    assert len(set(match.board_counts.values())) == len(match.board_counts)
    key = _answer_key(engine, lesson.id)
    assert key["correctOptionIds"][build.question_id] == "Hay tres tazas."
    assert [item["targetIds"] for item in key["questionEvaluations"]] == [
        ["say-quantity"], ["say-quantity", "plural-noun"], ["understand-quantity"],
    ]
    public = json.dumps(client.get(f"/api/v1/sessions/{sid}").json())
    assert "questionEvaluations" not in public and "correctOptionIds" not in public
    assert _draft(engine, sid)["missionPlan"] == [
        {"missionId": "M03", "practiceLevel": "A1", "contentVersion": 1}
    ]


def test_a_second_get_returns_the_same_m03_content(curated):
    profile, client = curated[2], curated[3]
    repository, sid, detail = _lesson(curated, _counts_only())
    again = repository.get(sid, profile.id)
    assert _m03(again).public_content == _m03(detail).public_content
    fetched = client.get(f"/api/v1/sessions/{sid}").json()
    repeated = client.get(f"/api/v1/sessions/{sid}").json()
    lesson = next(t for t in fetched["tasks"] if t["publicContent"].get("missionId") == "M03")
    other = next(t for t in repeated["tasks"] if t["publicContent"].get("missionId") == "M03")
    assert lesson == other


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


@pytest.mark.parametrize("scenario", ["correct", "partial", "incorrect"])
def test_m03_submissions_grade_each_question_once(curated, scenario):
    engine, _owner, _profile, client, *_ = curated
    _repository_, sid, detail = _lesson(curated, _counts_only())
    lesson = _m03(detail)
    choose, build, match = lesson.public_content.questions
    correct = _answer_key(engine, lesson.id)["correctOptionIds"]
    wrong_number = next(
        o.option_id for o in choose.options if o.option_id != correct[choose.question_id]
    )
    wrong_board = next(
        o.option_id for o in match.options if o.option_id != correct[match.question_id]
    )
    answers = {
        "correct": correct,
        "partial": {**correct, build.question_id: "Hay cuatro tazas."},
        "incorrect": {choose.question_id: wrong_number, build.question_id: "Hay tres taza.",
                      match.question_id: wrong_board},
    }[scenario]
    counted_groups = _draft(engine, sid)["countedGroups"]
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
    # Grading never rewrites the learner's saved counts.
    assert _draft(engine, sid)["countedGroups"] == counted_groups
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
        "correct": {qid: [] for qid in correct},
        "partial": {choose.question_id: [], match.question_id: [],
                    build.question_id: ["wrongQuantity"]},
        "incorrect": {choose.question_id: ["wrongQuantity"], match.question_id: ["wrongQuantity"],
                      build.question_id: ["pluralForm"]},
    }[scenario]
    assert mistakes == expected


def test_a_photo_fitting_all_three_plans_all_three(curated):
    engine, _owner, profile, *_ = curated
    repository, sid, detail = _lesson(curated, _everything)
    assert _planned(detail) == ["M01", "M02", "M03"]
    kinds = [task.kind for task in detail.tasks]
    assert kinds == ["vocabularyIntroduction", *["grammarLesson"] * 3]
    resumed = repository.get(sid, profile.id)
    assert [task.id for task in resumed.tasks] == [task.id for task in detail.tasks]
    assert [m.mission_id for m in repository._planned_missions(
        resumed.session.model_copy(update={"analysis_draft": _draft(engine, sid)}),
        {"proficiency_level": "A1", "target_language_code": "es"},
    )] == ["M01", "M02", "M03"]
    for task in detail.tasks[:-1]:
        repository.task_action(task.id, "skip", SkipTaskRequest())
    with pytest.raises(PracticeConflictError):
        repository.finish(sid, profile.id)
    repository.task_action(detail.tasks[-1].id, "skip", SkipTaskRequest())
    repository.finish(sid, profile.id)
    assert repository.get(sid, profile.id).session.status == "completed"


def test_a_saved_old_shape_m03_lesson_still_validates_and_loads(curated):
    """M03 v1 model-era lessons keep their saved public shape."""
    engine, owner, profile, client, *_ = curated
    _repository_, sid, _detail = _lesson(curated, _counts_only())
    content = {
        "kind": "grammarLesson", "focus": "sayHowMany", "title": "Say how many",
        "explanation": "Say how many with “Hay”, the number and the plural noun.",
        "questions": [
            {
                "questionId": "understand-quantity",
                "prompt": "What does “Hay tres tazas.” mean?",
                "options": [
                    {"optionId": "meaning-1", "label": "There are three cups."},
                    {"optionId": "meaning-2", "label": "There are four cups."},
                ],
            },
            {
                "questionId": "choose-quantity",
                "prompt": "How many cups are in your photo? Choose the sentence.",
                "options": [
                    {"optionId": "sentence-1", "label": "Hay tres tazas."},
                    {"optionId": "sentence-2", "label": "Hay tres taza."},
                    {"optionId": "sentence-3", "label": "Hay cuatro tazas."},
                ],
            },
            {
                "questionId": "build-quantity",
                "prompt": "Build the sentence with the word bank.",
                "interactionType": "sentenceBuilding",
                "tokenBank": ["tazas", "Hay", "tres", "."],
                "translation": "There are three cups.",
            },
        ],
        "missionId": "M03", "practiceLevel": "A1", "contentVersion": 1,
    }
    repository = PostgresTaskRepository(engine)
    saved = repository.create_task(SessionTask(
        session_id=sid, phase="learning", kind="grammarLesson", order_index=90,
        public_content=content,
        answer_key={"correctOptionIds": {}, "questionEvaluations": []},
    ), owner.id)
    assert repository.get(saved.id, owner.id).public_content == saved.public_content
    response = client.get(f"/api/v1/tasks/{saved.id}")
    assert response.status_code == 200, response.text
    loaded = _repository_.get(sid, profile.id)
    assert saved.id in {task.id for task in loaded.tasks}


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
