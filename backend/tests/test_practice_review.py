from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.practice import PracticeConflictError
from app.schemas.sessions import ReviewPracticeRequest


def test_processing_transition_preserves_draft_and_records_timeout_clock():
    from datetime import datetime

    from app.repositories.postgres.workflow import ALLOWED_TRANSITIONS
    from app.schemas.base import utc_now
    from app.schemas.enums import SessionStatus
    from app.schemas.sessions import Session

    assert set(ALLOWED_TRANSITIONS) == set(SessionStatus)
    draft = {"objects": [{"source_object_key": "object-1"}], "relations": []}
    session = Session(
        user_id=uuid4(),
        language_profile_id=uuid4(),
        scene_media_asset_id=uuid4(),
        status="awaitingObjectReview",
        analysis_draft=draft,
    )
    connection = MagicMock()
    connection.execute.return_value.rowcount = 1
    repository = PostgresWorkflowRepository(None, session.user_id)
    before = utc_now()
    processing = repository._transition(connection, session, "generatingTasks")
    assert processing.analysis_draft["objects"] == draft["objects"]
    assert processing.analysis_draft["relations"] == []
    assert (
        before
        <= datetime.fromisoformat(processing.analysis_draft["processingStartedAt"])
        <= utc_now()
    )
    assert "processingStartedAt" not in session.analysis_draft
    running = repository._transition(connection, processing, "inProgress")
    assert running.started_at is not None
    assert running.analysis_draft == processing.analysis_draft
    with pytest.raises(PracticeConflictError):
        repository._transition(connection, running, "analyzingScene")


def test_review_requires_unique_nonempty_selection_and_in_bounds_positions():
    object_id = uuid4()
    for body in [
        {"acceptedObjectIds": []},
        {"acceptedObjectIds": [str(object_id), str(object_id)]},
        {
            "acceptedObjectIds": [],
            "addedObjects": [{"id": str(object_id), "label": "window", "x": 1, "y": 0.2}],
        },
    ]:
        with pytest.raises(ValidationError):
            ReviewPracticeRequest.model_validate(body)
    review = ReviewPracticeRequest.model_validate(
        {
            "acceptedObjectIds": [],
            "addedObjects": [
                {
                    "id": str(object_id),
                    "label": " window ",
                    "x": 0.99,
                    "y": 0,
                }
            ],
        }
    )
    assert review.added_objects[0].label == "window"


def test_review_accepts_a_scene_title_and_repositioned_object_marker():
    object_id = uuid4()

    review = ReviewPracticeRequest.model_validate(
        {
            "sceneTitle": "A sunny cafe",
            "acceptedObjectIds": [str(object_id)],
            "repositionedObjects": [
                {"id": str(object_id), "anchorPoint": {"x": 0.45, "y": 0.6}}
            ],
        }
    )

    assert review.scene_title == "A sunny cafe"
    assert float(review.repositioned_objects[0].anchor_point.x) == 0.45
    with pytest.raises(ValidationError):
        ReviewPracticeRequest.model_validate(
            {
                "acceptedObjectIds": [str(object_id)],
                "repositionedObjects": [
                    {"id": str(object_id), "anchorPoint": {"x": 0.2, "y": 0.2}},
                    {"id": str(object_id), "anchorPoint": {"x": 0.4, "y": 0.4}},
                ],
            }
        )


@pytest.mark.parametrize("status", ["completed", "abandoned", "failed"])
def test_review_cannot_change_terminal_sessions(status):
    repo = PostgresWorkflowRepository(None, uuid4())
    connection = MagicMock()

    @contextmanager
    def transaction():
        yield connection

    repo.transaction = transaction
    repo._session = lambda *args: SimpleNamespace(status=status)
    with pytest.raises(PracticeConflictError):
        repo.review(uuid4(), uuid4(), ReviewPracticeRequest(accepted_object_ids=[uuid4()]))
    connection.execute.assert_not_called()


@pytest.mark.parametrize("status", ["inProgress", "completed", "skipped"])
def test_review_cannot_replace_started_tasks(status):
    repo = PostgresWorkflowRepository(None, uuid4())
    connection = MagicMock()

    @contextmanager
    def transaction():
        yield connection

    repo.transaction = transaction
    repo._session = lambda *args: SimpleNamespace(status="inProgress")
    repo._tasks = lambda *args: [SimpleNamespace(status=status)]
    with pytest.raises(PracticeConflictError):
        repo.review(uuid4(), uuid4(), ReviewPracticeRequest(accepted_object_ids=[uuid4()]))
    connection.execute.assert_not_called()


def test_review_rebuilds_tasks_only_for_selected_objects():
    from uuid import uuid5

    from app.schemas.media import SceneObject
    from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation

    session_id, profile_id = uuid4(), uuid4()
    words = [
        VocabularyItem(language_code="es", lemma=text, display_text=text, part_of_speech="noun")
        for text in ["silla", "mesa"]
    ]
    objects = [
        SceneObject(
            session_id=session_id,
            label=label,
            vocabulary_item_id=word.id,
            bounding_box={"x": 0.2, "y": 0.3, "width": 0.01, "height": 0.01},
        )
        for word, label in zip(words, ["chair", "table"], strict=True)
    ]
    translations = [
        VocabularyTranslation(
            vocabulary_item_id=word.id, source_language_code="en", translated_text=label
        )
        for word, label in zip(words, ["chair", "table"], strict=True)
    ]
    detail = SimpleNamespace(
        scene_objects=objects,
        scene_object_relations=[],
        vocabulary=words,
        translations=translations,
    )
    # Task generation runs in a second transaction after the rejected objects
    # were deleted, so it only ever sees the accepted ones.
    generated = SimpleNamespace(
        scene_objects=[objects[1]],
        scene_object_relations=[],
        vocabulary=words,
        translations=translations,
    )
    repo = PostgresWorkflowRepository(None, uuid4())
    connection = MagicMock()
    connection.execute.return_value.first.return_value = None
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "source_language_code": "en",
        "target_language_code": "es",
    }

    @contextmanager
    def transaction():
        yield connection

    repo.transaction = transaction
    repo._session = lambda *args: SimpleNamespace(
        id=session_id, status="inProgress", started_at=None
    )
    repo._tasks = lambda *args: []
    # Both generation phases read only the accepted objects: translation, then
    # the task build after the translation checkpoint has committed.
    repo._detail = MagicMock(side_effect=[detail, detail, generated, generated])
    repo.review(session_id, profile_id, ReviewPracticeRequest(accepted_object_ids=[objects[1].id]))
    inserted = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False) and call.args[0].table.name == "session_tasks"
    ]
    assert len(inserted) == 7
    assert all(
        task["scene_object_id"] in {None, objects[1].id} for task in inserted
    )
    introduction = next(task for task in inserted if task["kind"] == "vocabularyIntroduction")
    assert introduction["public_content"]["words"][0]["targetText"] == "mesa"
    assert introduction["public_content"]["words"][0]["translation"] == "table"
    # Same pending session can be reviewed again without changing generated task identity.
    assert introduction["id"] == uuid5(session_id, "placeholder-v1:vocabularyIntroduction")


def test_unknown_word_cannot_create_catalog_entries():
    repo = PostgresWorkflowRepository(None, uuid4())
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(PracticeConflictError, match="not in the vocabulary"):
        repo._catalog_word(
            connection, {"target_language_code": "es", "source_language_code": "en"}, "unknown"
        )
    assert all(call.args[0].is_select for call in connection.execute.call_args_list)


def test_analysis_saves_draft_without_scene_objects_or_tasks():
    from app.schemas.enums import SessionStatus
    from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
    from app.schemas.sessions import Session
    from app.services.scene_analysis import SceneAnalysisResult

    owner, profile = uuid4(), uuid4()
    asset = MediaAsset(
        owner_user_id=owner,
        source="userUpload",
        media_type="image",
        storage_key="test/photo.jpg",
        mime_type="image/jpeg",
    )
    session = Session(user_id=owner, language_profile_id=profile, scene_media_asset_id=asset.id)
    obj = SceneObject(
        session_id=session.id,
        label="chair",
        bounding_box={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
    )
    other = SceneObject(session_id=session.id, label="table")
    relation = SceneObjectRelation(
        subject_scene_object_id=obj.id,
        relation="beside",
        reference_scene_object_id=other.id,
        source_relation_key="provider:0",
    )
    repo = PostgresWorkflowRepository(None, owner)
    repo.analyzer = SimpleNamespace(
        analyze=lambda *args: SceneAnalysisResult(
            title="A title", summary="A summary.", objects=[obj, other], relations=[relation]
        )
    )
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one.side_effect = [
        asset.model_dump(),
        {},
    ]

    @contextmanager
    def transaction():
        yield connection

    repo.transaction = transaction
    repo._session = MagicMock(
        side_effect=[
            session,
            session.model_copy(update={"status": SessionStatus.ANALYZING_SCENE}),
        ]
    )
    repo._detail = lambda *args: "draft detail"
    assert repo.analyze(session.id, profile) == "draft detail"
    writes = [
        call.args[0] for call in connection.execute.call_args_list if not call.args[0].is_select
    ]
    assert len(writes) == 2
    assert all(write.table.name == "sessions" for write in writes)
    assert writes[0].compile().params["status"] == "analyzingScene"
    persist = writes[1].compile().params
    assert persist["status"] == "awaitingObjectReview"
    assert persist["session_title"] == "A title"
    assert persist["session_summary"] == "A summary."
    assert persist["analysis_draft"]["objects"][0]["id"] == str(obj.id)
    assert persist["analysis_draft"]["relations"][0]["source_relation_key"] == "provider:0"


def test_relations_require_selected_distinct_endpoints_and_no_duplicates():
    subject, reference = uuid4(), uuid4()
    relation = {
        "subjectSceneObjectId": str(subject),
        "relation": "beside",
        "referenceSceneObjectId": str(reference),
    }
    valid = ReviewPracticeRequest(
        accepted_object_ids=[subject],
        added_objects=[{"id": reference, "label": "table", "x": 0.2, "y": 0.3}],
        relations=[relation],
    )
    assert valid.relations[0].source_relation_key is None
    for relations in [
        [relation, relation],
        [{**relation, "referenceSceneObjectId": str(uuid4())}],
        [{**relation, "referenceSceneObjectId": str(subject)}],
        [{**relation, "relation": "  "}],
    ]:
        with pytest.raises(ValidationError):
            ReviewPracticeRequest(accepted_object_ids=[subject, reference], relations=relations)


def test_object_json_and_session_failure_contracts():
    from app.repositories.postgres.scene_objects import object_values, parse_object
    from app.schemas.media import SceneObject
    from app.schemas.sessions import Session

    obj = SceneObject(session_id=uuid4(), label="table", attributes={"color": "brown"})
    assert parse_object(object_values(obj)) == obj
    assert obj.bounding_box is None and obj.source_object_key is None
    obj.bounding_box = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    assert isinstance(object_values(obj)["bounding_box"]["x"], float)
    session = Session(
        user_id=uuid4(),
        language_profile_id=uuid4(),
        scene_media_asset_id=uuid4(),
        status="failed",
        failure_code="sceneAnalysisFailed",
    )
    assert session.model_dump(mode="json")["failureCode"] == "sceneAnalysisFailed"
    with pytest.raises(ValidationError):
        session.failure_code = "unrecognizedFailure"


def test_session_status_uses_database_enum_and_preserves_application_key():
    from sqlalchemy import insert, select, update
    from sqlalchemy.dialects.postgresql import dialect

    from app.repositories.postgres.practice import sessions
    from app.schemas.enums import SessionStatus

    column = sessions.c.status
    assert column.name == "session_status"
    assert column.type.name == "session_status"
    assert column.type.enums == [status.value for status in SessionStatus]
    assert column.type.result_processor(dialect(), None)("ready") is SessionStatus.READY
    for statement in [
        insert(sessions).values(id=uuid4(), status="created"),
        update(sessions).values(status="completed"),
    ]:
        compiled = statement.compile(dialect=dialect())
        assert "session_status" in str(compiled)
        assert compiled.params["status"] in {"created", "completed"}
    compiled = str(select(sessions.c.id).where(column == "inProgress").compile(dialect=dialect()))
    assert "sessions.session_status =" in compiled


def test_review_maps_manual_relation_endpoints_and_preserves_only_trusted_provenance():
    from uuid import uuid5

    from app.schemas.media import SceneObject, SceneObjectRelation
    from app.schemas.sessions import Session
    from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation

    session = Session(
        user_id=uuid4(),
        language_profile_id=uuid4(),
        scene_media_asset_id=uuid4(),
        status="awaitingObjectReview",
    )
    word = VocabularyItem(
        language_code="es", lemma="mesa", display_text="mesa", part_of_speech="noun"
    )
    translation = VocabularyTranslation(
        vocabulary_item_id=word.id, source_language_code="en", translated_text="table"
    )
    objects = [
        SceneObject(session_id=session.id, label=label, vocabulary_item_id=word.id)
        for label in ["chair", "table"]
    ]
    original = SceneObjectRelation(
        subject_scene_object_id=objects[0].id,
        reference_scene_object_id=objects[1].id,
        relation="beside",
        source_relation_key="ai:relation:1",
    )
    detail = SimpleNamespace(
        scene_objects=objects,
        scene_object_relations=[original],
        vocabulary=[word],
        translations=[translation],
    )
    connection = MagicMock()
    connection.execute.return_value.first.return_value = None
    repo = PostgresWorkflowRepository(None, session.user_id)

    @contextmanager
    def transaction():
        yield connection

    repo.transaction = transaction
    repo._session = lambda *args: session
    repo._tasks = lambda *args: []
    repo._detail = lambda *args: detail
    repo._catalog_word = lambda *args: word
    manual_id = uuid4()
    request = ReviewPracticeRequest(
        accepted_object_ids=[obj.id for obj in objects],
        added_objects=[{"id": manual_id, "label": "plant", "x": 0.1, "y": 0.2}],
        relations=[
            original,
            SceneObjectRelation(
                subject_scene_object_id=manual_id,
                reference_scene_object_id=objects[1].id,
                relation="on",
                source_relation_key="forged-ai-key",
            ),
        ],
    )
    repo.review(session.id, session.language_profile_id, request)
    writes = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False)
        and call.args[0].table.name == "scene_object_relations"
    ]
    assert len(writes) == 2
    assert writes[0]["source_relation_key"] == "ai:relation:1"
    assert writes[0]["id"] == original.id
    assert writes[1]["source_relation_key"] is None
    assert writes[1]["subject_scene_object_id"] == uuid5(session.id, "manual:" + str(manual_id))
