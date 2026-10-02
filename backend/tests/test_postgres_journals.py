from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from encounter_factory import create_encounter_task
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from test_postgres_sessions import database as database

from app.main import create_app
from app.repositories.journals import JournalConflictError
from app.repositories.postgres.journals import (
    PostgresJournalRepository,
    journal_revisions,
    journal_suggestions,
    journals,
)
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.vocabulary import (
    user_vocabulary_progress,
    vocabulary_encounters,
    vocabulary_items,
)
from app.repositories.postgres.xp import xp_events
from app.schemas.journals import (
    Journal,
    JournalDetailResponse,
    JournalSuggestion,
    JournalWordMention,
)
from app.schemas.media import MediaAsset
from app.schemas.vocabulary import UserVocabularyProgress, VocabularyEncounter, VocabularyItem


@pytest.fixture
def context(database, monkeypatch):
    engine, owner, profile, client = database
    task = create_encounter_task(engine, client, profile)
    words = [
        VocabularyItem(language_code="es", lemma=word, display_text=word, part_of_speech="noun")
        for word in ("mundo", "amigo")
    ]
    encounters = [
        VocabularyEncounter(
            user_id=owner.id,
            vocabulary_item_id=word.id,
            session_id=task.session_id,
            session_task_id=task.id,
            encounter_type="introduced",
            outcome="completed",
        )
        for word in words
    ]
    photo = MediaAsset(
        owner_user_id=owner.id,
        media_type="image",
        source="userUpload",
        storage_key=f"test/{uuid4()}",
        mime_type="image/jpeg",
    )
    audio = MediaAsset(
        owner_user_id=owner.id,
        media_type="audio",
        source="userUpload",
        storage_key=f"test/{uuid4()}",
        mime_type="audio/wav",
    )
    with engine.begin() as connection:
        for word, encounter in zip(words, encounters, strict=True):
            connection.execute(insert(vocabulary_items).values(**word.model_dump(by_alias=False)))
            progress = UserVocabularyProgress(user_id=owner.id, vocabulary_item_id=word.id)
            connection.execute(
                insert(user_vocabulary_progress).values(**progress.model_dump(by_alias=False))
            )
            connection.execute(
                insert(vocabulary_encounters).values(**encounter.model_dump(by_alias=False))
            )
        for asset in (photo, audio):
            connection.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
    repository = PostgresJournalRepository(engine, owner.id)
    yield engine, owner, profile, client, repository, words, encounters, photo, audio
    with engine.begin() as connection:
        connection.execute(delete(journals).where(journals.c.user_id == owner.id))
        connection.execute(delete(media_assets).where(media_assets.c.owner_user_id == owner.id))
        connection.execute(
            delete(user_vocabulary_progress).where(user_vocabulary_progress.c.user_id == owner.id)
        )
        connection.execute(
            delete(vocabulary_items).where(vocabulary_items.c.id.in_([word.id for word in words]))
        )


def save(client, profile, content="Hola 🌍 mundo", words=None):
    payload = {"languageProfileId": str(profile.id), "content": content, "title": "My day"}
    if words is not None:
        payload["selectedWords"] = words
    response = client.put("/api/v1/journal/today", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_daily_save_concurrent_revisions_and_restart(context):
    engine, owner, profile, client, repository, *_ = context
    with ThreadPoolExecutor(max_workers=6) as workers:
        saved = list(workers.map(lambda _: save(client, profile), range(6)))
    assert len({row["id"] for row in saved}) == 1
    entry = repository.read()[0]
    assert len(entry.revisions) == 1
    assert entry.journal.current_revision_id == entry.revisions[0].id
    endpoint = f"/api/v1/journals/{entry.journal.id}"
    with ThreadPoolExecutor(max_workers=4) as workers:
        responses = list(
            workers.map(
                lambda i: client.post(endpoint + "/revisions", json={"content": f"Revision {i}"}),
                range(4),
            )
        )
    assert all(row.status_code == 201 for row in responses)
    assert [row.revision_number for row in repository.read()[0].revisions] == [1, 2, 3, 4, 5]
    with TestClient(create_app()) as restarted:
        detail = restarted.get(endpoint)
        assert detail.status_code == 200
        assert len(detail.json()["revisions"]) == 5
        assert restarted.get("/api/v1/journal/today/context").json()["canCreate"] is False
    assert PostgresJournalRepository(engine, uuid4()).read() == []
    assert client.get(f"/api/v1/journals/{uuid4()}").status_code == 404


def test_media_audio_and_completion(context):
    engine, owner, profile, client, repository, words, encounters, photo, audio = context
    row = save(client, profile)
    endpoint = f"/api/v1/journals/{row['id']}"
    body = {"mediaAssetId": str(photo.id), "displayOrder": 0, "caption": "My photo"}
    first = client.post(endpoint + "/media", json=body)
    assert first.status_code == 201, first.text
    assert client.post(endpoint + "/media", json=body).json()["id"] == first.json()["id"]
    assert (
        client.post(endpoint + "/media", json=body | {"mediaAssetId": str(audio.id)}).status_code
        == 409
    )
    assert client.patch(endpoint, json={"audioMediaAssetId": str(audio.id)}).status_code == 200
    assert (
        client.patch(endpoint, json={"audioMediaAssetId": None}).json()["audioMediaAssetId"] is None
    )
    assert client.patch(endpoint, json={"audioMediaAssetId": str(photo.id)}).status_code == 409
    invalid = client.post(endpoint + "/complete", json={"currentRevisionId": str(uuid4())})
    assert invalid.status_code == 409
    body = {"currentRevisionId": row["currentRevisionId"]}
    completed = client.post(endpoint + "/complete", json=body)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert client.post(endpoint + "/complete", json=body).json() == completed.json()
    assert client.delete(endpoint + f"/media/{photo.id}").status_code == 204
    assert repository.read()[0].media == []
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(media_assets.c.id).where(media_assets.c.id == photo.id)
            ).scalar_one()
            == photo.id
        )
    cors = client.options(
        endpoint + f"/media/{photo.id}",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"},
    )
    assert cors.status_code == 200


def test_suggestion_accept_creates_revision_and_rejects_stale(context):
    _, owner, profile, client, repository, words, encounters, *_ = context
    row = save(client, profile)
    base_id = UUID(row["currentRevisionId"])
    suggestion = JournalSuggestion(
        journal_id=row["id"],
        base_revision_id=base_id,
        suggestion_type="vocabulary",
        start_offset=7,
        end_offset=12,
        original_text="mundo",
        suggested_text="amigo",
        explanation="Another word",
    )
    stale = JournalSuggestion(
        journal_id=row["id"],
        base_revision_id=base_id,
        suggestion_type="grammar",
        start_offset=0,
        end_offset=4,
        original_text="Hola",
        suggested_text="Saludos",
        explanation="Greeting",
    )
    mention = JournalWordMention(
        journal_revision_id=base_id,
        vocabulary_item_id=words[0].id,
        start_offset=7,
        end_offset=12,
        matched_text="mundo",
        match_method="exact",
        source_encounter_id=encounters[0].id,
    )

    def add(rows):
        rows[0].suggestions.extend([suggestion, stale])
        rows[0].word_mentions.append(mention)

    repository.change(add)
    endpoint = f"/api/v1/journal-suggestions/{suggestion.id}"
    accepted = client.post(endpoint + "/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert client.post(endpoint + "/accept").status_code == 200
    current = repository.read()[0]
    assert len(current.revisions) == 2
    assert current.revisions[-1].content == "Hola 🌍 amigo"
    assert current.revisions[-1].created_by == "merged"
    assert current.word_mentions[0].journal_revision_id == base_id
    assert client.post(f"/api/v1/journal-suggestions/{stale.id}/accept").status_code == 409
    assert client.post(f"/api/v1/journal-suggestions/{stale.id}/reject").status_code == 200
    assert client.post(endpoint + "/reject").status_code == 409


def test_bad_encounter_rolls_back_whole_write(context):
    _, owner, profile, client, repository, words, encounters, *_ = context
    row = save(client, profile)
    mention = JournalWordMention(
        journal_revision_id=row["currentRevisionId"],
        vocabulary_item_id=words[0].id,
        start_offset=7,
        end_offset=12,
        matched_text="mundo",
        match_method="exact",
        source_encounter_id=encounters[1].id,
    )

    def invalid(rows):
        rows[0].journal.title = "must roll back"
        rows[0].word_mentions.append(mention)

    with pytest.raises(JournalConflictError):
        repository.change(invalid)
    assert repository.read()[0].journal.title == "My day"
    assert repository.read()[0].word_mentions == []


def test_database_scope_revision_immutability_and_spans(context):
    engine, owner, profile, client, repository, *_ = context
    row = save(client, profile)
    other = Journal(
        user_id=owner.id,
        language_profile_id=profile.id,
        local_date=date.fromisoformat(row["localDate"]) - timedelta(days=1),
        timezone="UTC",
    )
    repository.change(lambda rows: rows.append(JournalDetailResponse(journal=other)))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(journals)
            .where(journals.c.id == other.id)
            .values(current_revision_id=UUID(row["currentRevisionId"]))
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(journal_revisions)
            .where(journal_revisions.c.id == UUID(row["currentRevisionId"]))
            .values(content="rewritten history")
        )
    suggestion = JournalSuggestion(
        journal_id=row["id"],
        base_revision_id=row["currentRevisionId"],
        suggestion_type="grammar",
        start_offset=0,
        end_offset=4,
        original_text="wrong",
        suggested_text="Hi",
        explanation="test",
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(journal_suggestions).values(**suggestion.model_dump(by_alias=False))
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(journals).where(journals.c.id == other.id).values(user_id=uuid4())
        )


def test_rls_and_cascade(context):
    engine, owner, profile, client, repository, *_ = context
    row = save(client, profile)
    with engine.begin() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relname IN "
                "('journals','journal_media','journal_revisions','journal_suggestions',"
                "'journal_word_mentions')"
            )
        ).scalar_one()
        assert count == 5
        connection.execute(delete(journals).where(journals.c.id == UUID(row["id"])))
        assert (
            connection.execute(
                select(journal_revisions).where(journal_revisions.c.journal_id == UUID(row["id"]))
            ).first()
            is None
        )
    assert repository.read() == []


def test_journal_words_mark_mastered_and_award_xp_once(context):
    engine, owner, profile, client, repository, words, *_ = context
    row = save(client, profile, words=[" Mundo ", "amigo", "not-in-my-bank"])
    journal_id = row["id"]
    with engine.connect() as connection:
        progress = {
            r["vocabulary_item_id"]: r
            for r in connection.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.user_id == owner.id
                )
            ).mappings()
        }
        assert progress[words[0].id]["status"] == "mastered"
        assert progress[words[0].id]["mastery_score"] == 1
        assert progress[words[1].id]["status"] == "mastered"

        def journal_xp():
            return connection.execute(
                select(func.sum(xp_events.c.amount))
                .select_from(xp_events)
                .where(
                    xp_events.c.user_id == owner.id,
                    xp_events.c.idempotency_key == f"journal:{journal_id}",
                )
            ).scalar_one()

        assert journal_xp() == 20
    # Editing the same journal never double-awards or double-counts exposures.
    update = client.patch(
        f"/api/v1/journals/{journal_id}",
        json={"selectedWords": ["mundo"], "content": "Segunda versión"},
    )
    assert update.status_code == 200, update.text
    with engine.connect() as connection:
        assert journal_xp() == 20
        row = (
            connection.execute(
                select(user_vocabulary_progress).where(
                    user_vocabulary_progress.c.user_id == owner.id,
                    user_vocabulary_progress.c.vocabulary_item_id == words[0].id,
                )
            )
            .mappings()
            .one()
        )
        assert row["exposure_count"] == 0 and row["status"] == "mastered"


def test_journal_entry_xp_independent_of_words(context):
    engine, owner, profile, client, repository, words, *_ = context
    row = save(client, profile, words=[])
    journal_id = row["id"]

    def journal_xp():
        with engine.connect() as connection:
            return connection.execute(
                select(func.sum(xp_events.c.amount))
                .select_from(xp_events)
                .where(
                    xp_events.c.user_id == owner.id,
                    xp_events.c.idempotency_key == f"journal:{journal_id}",
                )
            ).scalar_one()

    # A journal with no picked words still earns the journal award, once.
    assert journal_xp() == 20
    # Adding words on a later save marks them mastered but never re-awards.
    update = client.patch(f"/api/v1/journals/{journal_id}", json={"selectedWords": ["mundo"]})
    assert update.status_code == 200, update.text
    assert journal_xp() == 20
    with engine.connect() as connection:
        mastered = connection.execute(
            select(user_vocabulary_progress.c.status).where(
                user_vocabulary_progress.c.user_id == owner.id,
                user_vocabulary_progress.c.vocabulary_item_id == words[0].id,
            )
        ).scalar_one()
    assert mastered == "mastered"


def test_scoped_reads_limit_and_return_single_entries(context):
    _, owner, profile, client, repository, *_ = context
    row = save(client, profile)
    today = date.fromisoformat(row["localDate"])
    older = [
        Journal(
            user_id=owner.id,
            language_profile_id=profile.id,
            local_date=today - timedelta(days=offset),
            timezone="UTC",
        )
        for offset in (1, 2)
    ]

    def add(rows):
        rows.extend(JournalDetailResponse(journal=journal) for journal in older)

    repository.change(add)

    limited = repository.read_for_user(limit=2)
    assert [entry.journal.local_date for entry in limited] == [
        today,
        today - timedelta(days=1),
    ]
    assert [entry.journal.id for entry in limited] == [UUID(row["id"]), older[0].id]
    assert len(limited[0].revisions) == 1
    assert limited[0].revisions[0].journal_id == limited[0].journal.id

    one = repository.read_one(UUID(row["id"]))
    assert one is not None
    assert one.journal.id == UUID(row["id"])
    assert [revision.revision_number for revision in one.revisions] == [1]
    assert repository.read_one(uuid4()) is None

    by_date = repository.read_for_date(today - timedelta(days=2))
    assert by_date is not None
    assert by_date.journal.id == older[1].id
    assert repository.read_for_date(today - timedelta(days=9)) is None
