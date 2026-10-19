"""Shared PostgreSQL workflow assertions for M04 and M05 roleplay missions."""

from uuid import uuid4, uuid5

from sqlalchemy import func, select, update
from test_mission_m01_workflow import _analyzed, _answer_key, _attempt, _review
from test_preloaded_templates import SceneModel, services

from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.learner_history import snapshot_learner_history
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import task_attempts
from app.repositories.postgres.vocabulary import user_vocabulary_progress, vocabulary_encounters
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.schemas.sessions import AddedPracticeObject


def repository(curated, background=None):
    engine, owner = curated[:2]
    feature = services(SceneModel())
    return PostgresWorkflowRepository(
        engine,
        owner.id,
        translator=feature["translation"],
        learning_task_generator=feature["lessons"],
        ispy_clue_generator=feature["clues"],
        background=background,
    )


def lesson_task(detail, mission_id):
    return next(
        task for task in detail.tasks
        if task.public_content.mission_id == mission_id
    )


def review_lesson(
    curated,
    mission_id,
    added_objects=(),
    *,
    confirmed_object_limit=None,
    add_missing_roleplay_object=True,
    expect_omitted=False,
    include_attribute_snapshots=False,
):
    engine, _owner, profile, *_ = curated
    repo = repository(curated)
    session_id, analyzed = _analyzed(curated, repo)
    review_base = _review(analyzed)
    confirmed_objects = list(analyzed.scene_objects)
    if confirmed_object_limit is not None:
        confirmed_objects = confirmed_objects[:confirmed_object_limit]
    manual_objects = list(added_objects)
    if (
        add_missing_roleplay_object
        and mission_id in {"M04", "M05"}
        and len(confirmed_objects) + len(manual_objects) < 3
    ):
        manual_objects.append(
            AddedPracticeObject(
                id=uuid4(),
                label="toy",
                x=0.75,
                y=0.75,
            )
        )
    object_attributes = {
        obj.id: review_base.object_attributes[obj.id] for obj in confirmed_objects
    }
    attributes_before_plan = {
        str(object_id): attributes for object_id, attributes in object_attributes.items()
    }
    review_request = review_base.model_copy(update={
        "accepted_object_ids": [obj.id for obj in confirmed_objects],
        "object_attributes": object_attributes,
        "added_objects": manual_objects,
    })
    attributes_before_plan.update({
        str(uuid5(session_id, "manual:" + str(added.id))):
            review_request.object_attributes.get(added.id)
        for added in manual_objects
    })
    repo.review(session_id, profile.id, review_request)
    detail = repo.get(session_id, profile.id)
    task = next(
        (task for task in detail.tasks if task.public_content.mission_id == mission_id),
        None,
    )
    draft = detail.session.analysis_draft
    item = next(
        (item for item in draft["missionPlan"] if item["missionId"] == mission_id),
        None,
    )
    markers = draft["reviewMarkers"]
    if expect_omitted:
        assert item is None and task is None
        assert all(
            task.public_content.mission_id != mission_id for task in detail.tasks
        )
        return repo, session_id, detail, None, markers, []
    assert item is not None and task is not None
    facts = item["roleplayFacts"]
    expected_markers = {
        str(obj.id): index + 1 for index, obj in enumerate(confirmed_objects)
    }
    expected_markers.update({
        str(uuid5(session_id, "manual:" + str(item.id))):
            len(confirmed_objects) + index + 1
        for index, item in enumerate(manual_objects)
    })
    assert markers == expected_markers
    serialized = task.public_content.model_dump(mode="json", by_alias=True)
    assert serialized["roleplayFacts"] == facts
    fact_ids = {fact["sceneObjectId"] for fact in facts}
    assert fact_ids <= set(markers)
    questions = task.public_content.questions
    assert len(questions) == 3
    assert all(question.marker_object_ids is None for question in questions)
    assert all(
        str(question.scene_object_id) in fact_ids
        and markers[str(question.scene_object_id)] > 0
        for question in questions
    )
    role_object_ids = {
        tuple(fact.get("ownerNames", fact.get("subjectNames")) or []):
            fact["sceneObjectId"]
        for fact in facts
    }
    assert [
        str(question.scene_object_id) for question in questions
    ] == [role_object_ids[("Leo",)], role_object_ids[()], role_object_ids[("Ana",)]]
    first_get = task.public_content
    second_get = lesson_task(repo.get(session_id, profile.id), mission_id).public_content
    assert first_get == second_get
    result = (repo, session_id, detail, task, markers, facts)
    if include_attribute_snapshots:
        attributes_after_plan = {
            str(obj.id): obj.attributes for obj in detail.scene_objects
        }
        return (*result, attributes_before_plan, attributes_after_plan)
    return result


def _progress_snapshot(engine, user_id):
    with engine.connect() as connection:
        return connection.execute(
            select(
                user_vocabulary_progress.c.vocabulary_item_id,
                user_vocabulary_progress.c.status,
                user_vocabulary_progress.c.exposure_count,
                user_vocabulary_progress.c.correct_attempt_count,
                user_vocabulary_progress.c.mastery_score,
            )
            .where(user_vocabulary_progress.c.user_id == user_id)
            .order_by(user_vocabulary_progress.c.vocabulary_item_id)
        ).all()


def _scalar(engine, query):
    with engine.connect() as connection:
        return connection.execute(query).scalar_one()


def _profile_snapshot(engine, profile_id):
    with engine.connect() as connection:
        return dict(
            connection.execute(
                select(language_profiles).where(language_profiles.c.id == profile_id)
            ).mappings().one()
        )


def _learner_history_snapshot(engine, user_id, profile, session_id, scene_labels):
    with engine.connect() as connection:
        return snapshot_learner_history(
            connection, user_id, profile, session_id, scene_labels,
        )


def assert_grading_and_isolation(curated, mission_id, scenario):
    engine, owner, profile, client, *_ = curated
    profile_before = _profile_snapshot(engine, profile.id)
    (
        repo,
        session_id,
        detail,
        task,
        _markers,
        facts,
        attributes_before_plan,
        attributes_after_plan,
    ) = review_lesson(
        curated, mission_id, include_attribute_snapshots=True,
    )
    correct = _answer_key(engine, task.id)["correctOptionIds"]
    answers = {}
    for index, question in enumerate(task.public_content.questions):
        right = correct[question.question_id]
        wrong = next(
            (option.option_id for option in question.options if option.option_id != right),
            "This is not the assigned sentence.",
        )
        answers[question.question_id] = (
            right if scenario == "correct" or scenario == "partial" and index != 1 else wrong
        )
    progress_before = _progress_snapshot(engine, owner.id)
    progress_count_before = len(progress_before)
    encounters_before = _scalar(engine,
        select(func.count()).select_from(vocabulary_encounters).where(
            vocabulary_encounters.c.session_id == session_id,
        )
    )
    xp_before = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == session_id,
        xp_events.c.event_type == "taskCompleted",
    ))
    scene_labels = [obj.label for obj in detail.scene_objects]
    learner_history_before = _learner_history_snapshot(
        engine, owner.id, profile_before, session_id, scene_labels,
    )
    personalization_before = detail.session.analysis_draft.get("personalization")
    fact_ids = {fact["sceneObjectId"] for fact in facts}

    first = _attempt(client, task, answers, key=f"{mission_id}-{scenario}-{task.id}")
    assert first.status_code == 200, first.text
    result = first.json()["attempt"]
    expected = {
        question_id: answers[question_id] == correct[question_id]
        for question_id in correct
    }
    assert result["evaluationDetails"]["questionResults"] == expected
    encounters_after = _scalar(engine,
        select(func.count()).select_from(vocabulary_encounters).where(
            vocabulary_encounters.c.session_id == session_id,
        )
    )
    xp_after = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == session_id,
        xp_events.c.event_type == "taskCompleted",
    ))
    repeat = _attempt(client, task, answers, key=f"{mission_id}-{scenario}-{task.id}")
    assert repeat.status_code == 200
    assert repeat.json()["attempt"]["id"] == result["id"]
    assert encounters_after == encounters_before
    assert _scalar(engine, select(func.count()).select_from(vocabulary_encounters).where(
        vocabulary_encounters.c.session_id == session_id,
    )) == encounters_after
    if scenario == "correct":
        assert xp_after - xp_before == 1
    else:
        assert xp_after - xp_before in {0, 1}
    xp_after_repeat = _scalar(engine, select(func.count()).select_from(xp_events).where(
        xp_events.c.session_id == session_id,
        xp_events.c.event_type == "taskCompleted",
    ))
    assert xp_after_repeat == xp_after
    progress_after = _progress_snapshot(engine, owner.id)
    assert len(progress_after) == progress_count_before
    assert progress_after == progress_before
    assert _scalar(engine,
        select(func.count()).select_from(task_attempts).where(
            task_attempts.c.session_task_id == task.id,
        )
    ) == 1
    latest = client.get(f"/api/v1/tasks/{task.id}/latest-attempt")
    assert latest.status_code == 200
    assert latest.json()["attempt"]["answers"] == answers
    assert (
        latest.json()["attempt"]["reviewDetails"]["questionResults"]
        == result["evaluationDetails"]["questionResults"]
    )
    assert _scalar(engine,
        select(func.count()).select_from(vocabulary_encounters).where(
            vocabulary_encounters.c.session_task_id == task.id,
        )
    ) == 0
    restored = repo.get(session_id, profile.id)
    attributes_after_attempt = {
        str(obj.id): obj.attributes for obj in restored.scene_objects
    }
    for object_id in fact_ids:
        assert attributes_after_plan[object_id] == attributes_after_attempt[object_id]
        if object_id in attributes_before_plan:
            assert attributes_before_plan[object_id] == attributes_after_plan[object_id]
    assert _profile_snapshot(engine, profile.id) == profile_before
    assert _learner_history_snapshot(
        engine,
        owner.id,
        profile_before,
        session_id,
        scene_labels,
    ) == learner_history_before
    assert restored.session.analysis_draft.get("personalization") == personalization_before


class DeferredBackground:
    def __init__(self):
        self.jobs = []

    def submit(self, fn, /, *args, **kwargs):
        self.jobs.append((fn, args, kwargs))

    def run(self):
        for fn, args, kwargs in self.jobs:
            fn(*args, **kwargs)


def assert_tampered_facts_skip(curated, mission_id):
    engine, _owner, profile, *_ = curated
    queue = DeferredBackground()
    repo = repository(curated, queue)
    session_id, analyzed = _analyzed(curated, repo)
    added_objects = []
    if len(analyzed.scene_objects) < 3:
        added_objects.append(
            AddedPracticeObject(id=uuid4(), label="toy", x=0.75, y=0.75)
        )
    review_request = _review(analyzed).model_copy(
        update={"added_objects": added_objects}
    )
    repo.review(session_id, profile.id, review_request)
    with engine.begin() as connection:
        draft = connection.execute(
            select(sessions.c.analysis_draft).where(sessions.c.id == session_id)
        ).scalar_one()
        item = next(
            item for item in draft["missionPlan"] if item["missionId"] == mission_id
        )
        item["roleplayFacts"][0]["source"] = "inferred"
        connection.execute(
            update(sessions).where(sessions.c.id == session_id).values(analysis_draft=draft)
        )
    queue.run()
    detail = repo.get(session_id, profile.id)
    assert detail.session.analysis_draft["skippedMissions"] == [
        {"missionId": mission_id, "reason": "invalidRoleplay"}
    ]
    assert all(task.public_content.mission_id != mission_id for task in detail.tasks)
