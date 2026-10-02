import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from encounter_factory import create_encounter_task
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import create_database_engine
from app.main import create_app
from app.repositories.learning import LearningStorageError
from app.repositories.postgres.language_profiles import (
    PostgresLanguageProfileRepository,
)
from app.repositories.postgres.media_assets import (
    PostgresMediaAssetRepository,
    media_assets,
)
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scenes import preloaded_scenes
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import (
    PostgresVocabularyRepository,
    VocabularyEncounterConflictError,
    user_vocabulary_progress,
    vocabulary_encounters,
    vocabulary_items,
    vocabulary_translations,
)
from app.repositories.postgres.xp import xp_events
from app.schemas.base import utc_now
from app.schemas.enums import VocabularyEncounterOutcome
from app.schemas.media import MediaAsset
from app.schemas.users import LanguageProfile, User
from app.schemas.vocabulary import (
    UserVocabularyProgress,
    VocabularyEncounter,
    VocabularyItem,
    VocabularyTranslation,
)


def test_progress_count_validation():
    with pytest.raises(ValidationError):
        UserVocabularyProgress(user_id=uuid4(), vocabulary_item_id=uuid4(), correct_attempt_count=1)


def test_storage_errors():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("select", {}, Exception("secret"))
    repository = PostgresVocabularyRepository(engine)
    with pytest.raises(LearningStorageError):
        repository.list_vocabulary(uuid4())


@pytest.fixture
def database(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    owner = User(display_name="Vocabulary test", auth_provider_id=f"test-{uuid4()}")
    monkeypatch.setenv("DEMO_USER_ID", str(owner.id))
    with engine.begin() as connection:
        connection.execute(insert(users).values(**owner.model_dump(by_alias=False)))
    PostgresLanguageProfileRepository(engine).create(
        LanguageProfile(
            user_id=owner.id,
            source_language_code="en",
            target_language_code="es",
            proficiency_level="A1",
        )
    )
    ids = []
    media_ids = []
    from app.schemas.vocabulary import VocabularyItem

    with engine.begin() as connection:
        for word in ["calle", "autobus", "arbol"]:
            item = VocabularyItem(
                language_code="es", lemma=word, display_text=word, part_of_speech="noun"
            )
            ids.append(item.id)
            translation = VocabularyTranslation(
                vocabulary_item_id=item.id,
                source_language_code="en",
                translated_text=f"Translation of {word}",
            )
            progress = UserVocabularyProgress(user_id=owner.id, vocabulary_item_id=item.id)
            connection.execute(insert(vocabulary_items).values(**item.model_dump(by_alias=False)))
            connection.execute(
                insert(vocabulary_translations).values(**translation.model_dump(by_alias=False))
            )
            connection.execute(
                insert(user_vocabulary_progress).values(
                    **progress.model_dump(by_alias=False)
                )
            )
    repository = PostgresVocabularyRepository(engine)
    try:
        yield engine, owner, ids, media_ids, repository
    finally:
        with engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id == owner.id))
            connection.execute(delete(vocabulary_items).where(vocabulary_items.c.id.in_(ids)))
            connection.execute(delete(media_assets).where(media_assets.c.id.in_(media_ids)))
        engine.dispose()


def test_api_pagination_translation_and_isolation(database, monkeypatch):
    engine, owner, ids, _, repository = database
    with TestClient(create_app()) as client:
        first = client.get("/api/v1/me/vocabulary?limit=2")
        assert first.status_code == 200
        page = first.json()
        assert len(page["items"]) == 2 and page["nextCursor"]
        second = client.get(
            "/api/v1/me/vocabulary", params={"cursor": page["nextCursor"], "limit": 2}
        ).json()
        assert len(second["items"]) == 1 and second["nextCursor"] is None
        assert len({row["vocabulary"]["id"] for row in page["items"] + second["items"]}) == 3
        # sceneId/topic derive from the latest encounter; seed words have none yet.
        assert all(row["sceneId"] is None and row["topic"] is None for row in page["items"])
        assert client.get("/api/v1/me/vocabulary?cursor=invalid").status_code == 400
        other = User(display_name="Other", auth_provider_id=f"test-{uuid4()}")
        with engine.begin() as connection:
            connection.execute(insert(users).values(**other.model_dump(by_alias=False)))
        try:
            PostgresLanguageProfileRepository(engine).create(
                LanguageProfile(
                    user_id=other.id,
                    source_language_code="en",
                    target_language_code="es",
                    proficiency_level="A1",
                )
            )
            assert repository.list_vocabulary(other.id) == []
            monkeypatch.setenv("DEMO_USER_ID", str(other.id))
            assert client.get("/api/v1/me/vocabulary").json()["items"] == []
        finally:
            with engine.begin() as connection:
                connection.execute(delete(users).where(users.c.id == other.id))
    french = VocabularyTranslation(
        vocabulary_item_id=ids[0], source_language_code="FR", translated_text="rue"
    )
    with engine.begin() as connection:
        connection.execute(
            insert(vocabulary_translations).values(**french.model_dump(by_alias=False))
        )
    PostgresLanguageProfileRepository(engine).create(
        LanguageProfile(
            user_id=owner.id,
            source_language_code="fr",
            target_language_code="es",
            proficiency_level="A1",
        )
    )
    words = repository.list_vocabulary(owner.id)
    assert (
        next(row for row in words if row.vocabulary.id == ids[0]).translation.translated_text
        == "rue"
    )
    assert sum(row.translation is None for row in words) == 2
    PostgresLanguageProfileRepository(engine).create(
        LanguageProfile(
            user_id=owner.id,
            source_language_code="en",
            target_language_code="de",
            proficiency_level="A1",
        )
    )
    assert repository.list_vocabulary(owner.id) == []


@pytest.fixture
def encounter_task(database):
    engine, owner, *_ = database
    profile = PostgresLanguageProfileRepository(engine).list_for_user(owner.id)[0]
    with TestClient(create_app()) as client:
        return create_encounter_task(engine, client, profile)


def test_concurrent_encounters_are_idempotent_and_atomic(database, encounter_task):
    engine, owner, ids, _, repository = database
    event = VocabularyEncounter(
        user_id=owner.id,
        vocabulary_item_id=ids[0],
        session_id=encounter_task.session_id,
        session_task_id=encounter_task.id,
        encounter_type="practised",
        outcome="correct",
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(repository.record_encounter, [event] * 8))
    word = next(row for row in repository.list_vocabulary(owner.id) if row.vocabulary.id == ids[0])
    assert word.encounter_ids == [event.id]
    assert word.progress.exposure_count == word.progress.correct_attempt_count == 1
    assert word.progress.last_practised_at == event.occurred_at
    assert word.progress.first_learned_at == event.occurred_at
    with pytest.raises(VocabularyEncounterConflictError):
        repository.record_encounter(
            VocabularyEncounter.model_validate(
                event.model_dump(by_alias=False) | {"outcome": "incorrect"}
            )
        )
    more = [event.model_copy(update={"id": uuid4()}) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(repository.record_encounter, more))
    word = next(row for row in repository.list_vocabulary(owner.id) if row.vocabulary.id == ids[0])
    assert word.progress.exposure_count == word.progress.correct_attempt_count == 9
    assert len(word.encounter_ids) == 9
    assert (
        next(
            row for row in repository.list_vocabulary(owner.id) if row.vocabulary.id == ids[0]
        ).progress.exposure_count
        == 9
    )
    unknown = uuid4()
    with pytest.raises(LearningStorageError):
        repository.record_encounter(
            event.model_copy(update={"id": uuid4(), "vocabulary_item_id": unknown})
        )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.vocabulary_item_id == unknown
                )
            ).first()
            is None
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"status": "bad"},
        {"exposure_count": -1},
        {"correct_attempt_count": -1},
        {"correct_attempt_count": 1},
        {"mastery_score": Decimal("1.1")},
    ],
)
def test_progress_constraints(database, patch):
    engine, _, ids, _, _ = database
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(user_vocabulary_progress)
            .where(user_vocabulary_progress.c.vocabulary_item_id == ids[0])
            .values(**patch)
        )


def test_relations_uniqueness_and_rls(database):
    engine, owner, ids, _, _ = database
    duplicate = VocabularyTranslation(
        vocabulary_item_id=ids[0], source_language_code="EN", translated_text="duplicate"
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(vocabulary_translations).values(**duplicate.model_dump(by_alias=False))
        )
    duplicate_progress = UserVocabularyProgress(user_id=owner.id, vocabulary_item_id=ids[0])
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(user_vocabulary_progress).values(**duplicate_progress.model_dump(by_alias=False))
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(delete(vocabulary_items).where(vocabulary_items.c.id == ids[0]))
    with engine.connect() as connection:
        for table in [
            vocabulary_items,
            vocabulary_translations,
            user_vocabulary_progress,
            vocabulary_encounters,
        ]:
            assert connection.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = CAST(:name AS regclass)"),
                {"name": f"public.{table.name}"},
            ).scalar_one()


def test_pronunciation_audio_relation(database):
    engine, _, ids, media_ids, _ = database
    audio = MediaAsset(
        media_type="audio", source="preloaded", mime_type="audio/ogg", storage_key=f"test/{uuid4()}"
    )
    image = MediaAsset(
        media_type="image", source="preloaded", mime_type="image/png", storage_key=f"test/{uuid4()}"
    )
    for asset in [audio, image]:
        media_ids.append(asset.id)
        PostgresMediaAssetRepository(engine).create(asset)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(vocabulary_items)
            .where(vocabulary_items.c.id == ids[0])
            .values(pronunciation_audio_asset_id=image.id)
        )
    with engine.begin() as connection:
        connection.execute(
            update(vocabulary_items)
            .where(vocabulary_items.c.id == ids[0])
            .values(pronunciation_audio_asset_id=audio.id)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(media_assets)
            .where(media_assets.c.id == audio.id)
            .values(media_type="image", mime_type="image/png")
        )
    with engine.begin() as connection:
        connection.execute(delete(media_assets).where(media_assets.c.id == audio.id))
        assert (
            connection.execute(
                select(vocabulary_items.c.pronunciation_audio_asset_id).where(
                    vocabulary_items.c.id == ids[0]
                )
            ).scalar_one()
            is None
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"outcome": "invalid"},
        {"encounter_type": "invalid"},
        {"user_id": uuid4()},
        {"vocabulary_item_id": uuid4()},
        {"session_id": None},
    ],
)
def test_encounter_database_constraints(database, encounter_task, patch):
    engine, owner, ids, _, _ = database
    event = VocabularyEncounter(
        user_id=owner.id,
        vocabulary_item_id=ids[0],
        session_id=encounter_task.session_id,
        session_task_id=encounter_task.id,
        encounter_type="introduced",
        outcome="completed",
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(vocabulary_encounters).values(**(event.model_dump(by_alias=False) | patch))
        )


@pytest.mark.parametrize(
    "invalid", ["missing_session", "missing_task", "other_session", "other_user"]
)
def test_encounter_parent_links_and_counter_rollback(
    database, encounter_task, monkeypatch, invalid
):
    engine, owner, ids, _, repository = database
    other = User(display_name="Other", auth_provider_id=f"test-{uuid4()}")
    event = VocabularyEncounter(
        user_id=owner.id,
        vocabulary_item_id=ids[0],
        session_id=encounter_task.session_id,
        session_task_id=encounter_task.id,
        encounter_type="practised",
        outcome="correct",
    )
    expected_constraint = "vocabulary_encounters_task_session_fkey"
    if invalid == "missing_session":
        event.session_id = uuid4()
        expected_constraint = "vocabulary_encounters_session_owner_fkey"
    elif invalid == "missing_task":
        event.session_task_id = uuid4()
    elif invalid == "other_session":
        profile = PostgresLanguageProfileRepository(engine).list_for_user(owner.id)[0]
        with TestClient(create_app()) as client:
            # The open session must be closed before a second session can exist.
            assert (
                client.post(f"/api/v1/sessions/{encounter_task.session_id}/abandon").status_code
                == 200
            )
            event.session_task_id = create_encounter_task(engine, client, profile).id
    else:
        # A valid progress pair ensures the new owner FK, rather than the old progress FK,
        # is what rejects the reference to someone else's existing session and task.
        with engine.begin() as connection:
            connection.execute(insert(users).values(**other.model_dump(by_alias=False)))
            progress = UserVocabularyProgress(user_id=other.id, vocabulary_item_id=ids[0])
            connection.execute(
                insert(user_vocabulary_progress).values(**progress.model_dump(by_alias=False))
            )
        event.user_id = other.id
        expected_constraint = "vocabulary_encounters_session_owner_fkey"
    try:
        with pytest.raises(IntegrityError) as error, engine.begin() as connection:
            connection.execute(
                insert(vocabulary_encounters).values(**event.model_dump(by_alias=False))
            )
        assert error.value.orig.diag.constraint_name == expected_constraint
        with pytest.raises(LearningStorageError):
            repository.record_encounter(event)
        with engine.connect() as connection:
            progress = (
                connection.execute(
                    select(user_vocabulary_progress).where(
                        user_vocabulary_progress.c.user_id == event.user_id,
                        user_vocabulary_progress.c.vocabulary_item_id == ids[0],
                    )
                )
                .mappings()
                .one()
            )
            assert progress["exposure_count"] == progress["correct_attempt_count"] == 0
            assert (
                connection.execute(
                    select(vocabulary_encounters).where(vocabulary_encounters.c.id == event.id)
                ).first()
                is None
            )
    finally:
        if invalid == "other_user":
            with engine.begin() as connection:
                connection.execute(delete(users).where(users.c.id == other.id))


@pytest.mark.parametrize("parent", ["session", "task", "user"])
def test_encounter_links_cascade_deletion(database, encounter_task, parent):
    from app.repositories.postgres.practice import sessions
    from app.repositories.postgres.tasks import session_tasks

    engine, owner, ids, _, repository = database
    event = repository.record_encounter(
        VocabularyEncounter(
            user_id=owner.id,
            vocabulary_item_id=ids[0],
            session_id=encounter_task.session_id,
            session_task_id=encounter_task.id,
            encounter_type="introduced",
            outcome="completed",
        )
    )
    for field in ["session_id", "session_task_id"]:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                update(vocabulary_encounters)
                .where(vocabulary_encounters.c.id == event.id)
                .values(**{field: uuid4()})
            )
    with engine.begin() as connection:
        table, parent_id = {
            "session": (sessions, event.session_id),
            "task": (session_tasks, event.session_task_id),
            "user": (users, owner.id),
        }[parent]
        connection.execute(delete(table).where(table.c.id == parent_id))
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(vocabulary_encounters).where(vocabulary_encounters.c.id == event.id)
            ).first()
            is None
        )

        if parent != "user":
            progress = (
                connection.execute(
                    select(user_vocabulary_progress).where(
                        user_vocabulary_progress.c.user_id == owner.id,
                        user_vocabulary_progress.c.vocabulary_item_id == ids[0],
                    )
                )
                .mappings()
                .one()
            )
            assert progress["exposure_count"] == progress["correct_attempt_count"] == 0
            assert progress["first_learned_at"] is None
            assert connection.execute(
                select(vocabulary_items.c.id).where(vocabulary_items.c.id == ids[0])
            ).first()


def progress_row(engine, user_id, item_id):
    with engine.connect() as connection:
        return (
            connection.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.user_id == user_id,
                    user_vocabulary_progress.c.vocabulary_item_id == item_id,
                )
            )
            .mappings()
            .one()
        )


def test_status_ladder_mastery_and_replay(database, encounter_task):
    engine, owner, ids, _, repository = database

    def encounter(item_id, encounter_type, outcome, event_id=None):
        return VocabularyEncounter(
            id=event_id or uuid4(),
            user_id=owner.id,
            vocabulary_item_id=item_id,
            session_id=encounter_task.session_id,
            session_task_id=encounter_task.id,
            encounter_type=encounter_type,
            outcome=outcome,
        )

    introduced = encounter(ids[0], "introduced", "completed")
    assert repository.record_encounter(introduced).id == introduced.id
    row = progress_row(engine, owner.id, ids[0])
    assert row["status"] == "new" and row["mastery_score"] == 0
    assert row["exposure_count"] == 1 and row["last_practised_at"] is None

    practised = encounter(ids[0], "practised", "correct")
    repository.record_encounter(practised)
    row = progress_row(engine, owner.id, ids[0])
    assert row["status"] == "learning" and row["mastery_score"] == Decimal("0.5")
    assert row["exposure_count"] == 2 and row["correct_attempt_count"] == 1
    assert row["last_practised_at"] == practised.occurred_at

    # An out-of-order write can never move last_practised_at backwards.
    earlier = practised.model_copy(
        update={"id": uuid4(), "occurred_at": practised.occurred_at - timedelta(days=1)}
    )
    repository.record_encounter(earlier)
    row = progress_row(engine, owner.id, ids[0])
    assert row["last_practised_at"] == practised.occurred_at
    assert row["exposure_count"] == 3

    # Replays of the same event id never move counters again.
    assert repository.record_encounter(practised).id == practised.id
    row = progress_row(engine, owner.id, ids[0])
    assert row["exposure_count"] == 3 and row["correct_attempt_count"] == 2
    with pytest.raises(VocabularyEncounterConflictError):
        repository.record_encounter(
            practised.model_copy(update={"outcome": VocabularyEncounterOutcome.INCORRECT})
        )

    profile = PostgresLanguageProfileRepository(engine).list_for_user(owner.id)[0]
    resolved = repository.record_journal_usage(
        user_id=owner.id,
        language_profile_id=profile.id,
        journal_id=uuid4(),
        words=["CALLE", "not-a-real-word"],
        occurred_at=utc_now(),
    )
    assert resolved == [ids[0]]
    row = progress_row(engine, owner.id, ids[0])
    assert row["status"] == "mastered" and row["mastery_score"] == 1

    # Journal evidence is not an encounter and never counts as exposure.
    assert row["exposure_count"] == 3 and row["correct_attempt_count"] == 2

    # A later practice encounter cannot downgrade mastered, and nothing emits familiar.
    repository.record_encounter(encounter(ids[0], "practised", "incorrect"))
    row = progress_row(engine, owner.id, ids[0])
    assert row["status"] == "mastered" and row["mastery_score"] == 1
    assert row["exposure_count"] == 4
    with engine.connect() as connection:
        statuses = (
            connection.execute(
                select(user_vocabulary_progress.c.status).where(
                    user_vocabulary_progress.c.user_id == owner.id
                )
            )
            .scalars()
            .all()
        )
    assert "familiar" not in statuses


def test_journal_usage_scoping_and_xp_once(database, encounter_task):
    engine, owner, ids, _, repository = database
    profile = PostgresLanguageProfileRepository(engine).list_for_user(owner.id)[0]
    other = User(display_name="Other", auth_provider_id=f"test-{uuid4()}")
    german = VocabularyItem(
        language_code="de", lemma="calle", display_text="calle", part_of_speech="noun"
    )
    other_progress = UserVocabularyProgress(user_id=other.id, vocabulary_item_id=ids[1])
    with engine.begin() as connection:
        connection.execute(insert(users).values(**other.model_dump(by_alias=False)))
        connection.execute(insert(vocabulary_items).values(**german.model_dump(by_alias=False)))
        connection.execute(
            insert(user_vocabulary_progress).values(**other_progress.model_dump(by_alias=False))
        )
    try:
        journal_id = uuid4()
        resolved = repository.record_journal_usage(
            user_id=owner.id,
            language_profile_id=profile.id,
            journal_id=journal_id,
            words=["autobus", "calle", "missing"],
            occurred_at=utc_now(),
        )
        # 'calle' also names a German item, but only the owner's own
        # target-language progress rows are evidence; 'missing' is ignored.
        assert set(resolved) == {ids[0], ids[1]}
        for item_id in (ids[0], ids[1]):
            row = progress_row(engine, owner.id, item_id)
            assert row["status"] == "mastered" and row["mastery_score"] == 1
            assert row["last_practised_at"] is not None
        # Another user's progress on the same word is untouched.
        assert progress_row(engine, other.id, ids[1])["status"] == "new"
        # The German item never received a progress row for the owner.
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(user_vocabulary_progress).where(
                        user_vocabulary_progress.c.user_id == owner.id,
                        user_vocabulary_progress.c.vocabulary_item_id == german.id,
                    )
                ).first()
                is None
            )

        # A profile owned by someone else resolves nothing and awards nothing.
        assert (
            repository.record_journal_usage(
                user_id=owner.id,
                language_profile_id=uuid4(),
                journal_id=uuid4(),
                words=["autobus"],
                occurred_at=utc_now(),
            )
            == []
        )

        def journal_events():
            with engine.connect() as connection:
                return connection.execute(
                    select(func.count())
                    .select_from(xp_events)
                    .where(
                        xp_events.c.user_id == owner.id,
                        xp_events.c.idempotency_key == f"journal:{journal_id}",
                    )
                ).scalar_one()

        assert journal_events() == 1
        repository.record_journal_usage(
            user_id=owner.id,
            language_profile_id=profile.id,
            journal_id=journal_id,
            words=["autobus"],
            occurred_at=utc_now(),
        )
        assert journal_events() == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id == other.id))
            connection.execute(delete(vocabulary_items).where(vocabulary_items.c.id == german.id))


def test_scene_and_topic_derived_from_latest_encounter(database, encounter_task):
    engine, owner, ids, _, repository = database
    repository.record_encounter(
        VocabularyEncounter(
            user_id=owner.id,
            vocabulary_item_id=ids[0],
            session_id=encounter_task.session_id,
            session_task_id=encounter_task.id,
            encounter_type="practised",
            outcome="correct",
        )
    )
    with engine.connect() as connection:
        slug, title = connection.execute(
            select(preloaded_scenes.c.slug, preloaded_scenes.c.title)
            .select_from(preloaded_scenes)
            .join(
                sessions,
                sessions.c.scene_media_asset_id == preloaded_scenes.c.media_asset_id,
            )
            .where(sessions.c.id == encounter_task.session_id)
            .where(preloaded_scenes.c.language_code == "es")
        ).one()
    items = {row.vocabulary.id: row for row in repository.list_vocabulary(owner.id)}
    assert items[ids[0]].scene_id == slug and items[ids[0]].topic == title
    # No encounters yet and an uploaded scene both produce None.
    assert items[ids[1]].scene_id is None and items[ids[1]].topic is None

    asset = MediaAsset(
        owner_user_id=owner.id,
        source="userUpload",
        media_type="image",
        storage_key=f"test/{uuid4()}.jpg",
        mime_type="image/jpeg",
    )
    upload_session = uuid4()
    upload_task = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
        connection.execute(
            insert(sessions).values(
                id=upload_session,
                user_id=owner.id,
                language_profile_id=connection.execute(
                    select(sessions.c.language_profile_id).where(
                        sessions.c.id == encounter_task.session_id
                    )
                ).scalar_one(),
                scene_media_asset_id=asset.id,
                status="completed",
                completed_at=utc_now(),
            )
        )
        connection.execute(
            insert(session_tasks).values(
                id=upload_task,
                session_id=upload_session,
                phase="learning",
                kind="reflection",
                order_index=0,
                public_content={"kind": "reflection", "prompt": "Write"},
            )
        )
        connection.execute(
            insert(vocabulary_encounters).values(
                **VocabularyEncounter(
                    user_id=owner.id,
                    vocabulary_item_id=ids[2],
                    session_id=upload_session,
                    session_task_id=upload_task,
                    encounter_type="practised",
                    outcome="correct",
                ).model_dump(by_alias=False)
            )
        )
    items = {row.vocabulary.id: row for row in repository.list_vocabulary(owner.id)}
    assert items[ids[2]].scene_id is None and items[ids[2]].topic is None
    assert len(items[ids[2]].scenes) == 1
    assert items[ids[2]].scenes[0].media_asset_id == asset.id
    assert items[ids[2]].scenes[0].title == "Your photo"
    assert items[ids[1]].scenes == []
    assert items[ids[0]].scenes[0].scene_id == slug

    # Repeated practice in the uploaded image retains one photo association,
    # and a word encountered in two images remains linked to both.
    for _ in range(2):
        repository.record_encounter(
            VocabularyEncounter(
                user_id=owner.id,
                vocabulary_item_id=ids[0],
                session_id=upload_session,
                session_task_id=upload_task,
                encounter_type="practised",
                outcome="correct",
            )
        )
    items = {row.vocabulary.id: row for row in repository.list_vocabulary(owner.id)}
    assert len(items[ids[0]].scenes) == 2
    assert {scene.scene_id for scene in items[ids[0]].scenes} == {slug, None}
    with engine.begin() as connection:
        connection.execute(delete(sessions).where(sessions.c.id == upload_session))
        connection.execute(delete(media_assets).where(media_assets.c.id == asset.id))
