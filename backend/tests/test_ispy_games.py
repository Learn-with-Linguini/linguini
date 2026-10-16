"""Standalone I-Spy games play a fixed snapshot of the latest confirmed lesson scene."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update
from test_postgres_sessions import create_run, upload_asset
from test_postgres_sessions import database as database

from app.ai.features.ispy_clues import ISpyClueGenerationError
from app.ai.features.ispy_clues.schemas import GeneratedISpyClue, ISpyClueResult
from app.ai.features.ispy_guess import ISpyGuessResult
from app.ai.features.translation.schemas import SceneTranslationResult
from app.repositories.postgres.ispy_games import CONFIRM_SCENE_FIRST, PostgresISpyGameRepository
from app.repositories.postgres.language_profiles import PostgresLanguageProfileRepository
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.scenes import preloaded_scenes
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import vocabulary_encounters
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.postgres.xp import xp_events
from app.repositories.practice import PracticeConflictError, PracticeNotFoundError
from app.schemas.base import utc_now
from app.schemas.enums import SceneRelationType
from app.schemas.ispy import StartISpyGameRequest
from app.schemas.media import SceneObjectRelation
from app.schemas.sessions import (
    AddedPracticeObject,
    CreateSessionRequest,
    RepositionedPracticeObject,
    ReviewPracticeRequest,
)
from app.schemas.tasks import LatestClueAttempt, SkipTaskRequest, TaskAttempt
from app.schemas.users import LanguageProfile, User


class Translator:
    def __init__(self):
        self.payloads = []

    def translate(self, payload, cache_scope=None, **_options):
        self.payloads.append(payload)
        prefix = payload["targetLanguage"]
        return SceneTranslationResult.model_validate({
            kind: [
                {**term, "translation": f"{prefix}-{term['source']}", "phoneticText": "AH"}
                for term in payload[kind]
            ]
            for kind in ("objects", "attributes", "relationships")
        })


class Clues:
    def __init__(self):
        self.payloads = []
        self.error = None

    def generate(self, payload, **_options):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        key = payload["objects"][0]["key"]
        return ISpyClueResult(clues=[
            GeneratedISpyClue(clue="es rojo", answer_object_key=key, object_keys=[key])
        ])


class Guesser:
    def guess(self, context, learner_text, *, session_id=None):
        return ISpyGuessResult(
            guessed_object_key=None, ambiguous=True, alternative_object_keys=[],
            matched_evidence_keys=[], contradicted_evidence_keys=[], feedback="Try again.",
        )


@pytest.fixture
def repos(database):
    engine, owner, profile, _client = database
    translator, clues = Translator(), Clues()
    workflow = PostgresWorkflowRepository(
        engine, owner.id, translator=translator,
        ispy_clue_generator=clues, ispy_guess_generator=Guesser(),
    )
    return workflow, PostgresISpyGameRepository(workflow), profile, translator, clues


def confirmed_lesson(workflow, profile, asset_id, key, *, colour="red", anchor=(0.7, 0.2)):
    """Review with one removed object, one recoloured and moved, one added, and a relation."""
    sid = workflow.create(CreateSessionRequest(
        language_profile_id=profile.id, media_asset_id=asset_id, idempotency_key=key
    )).session.id
    workflow.analyze(sid, profile.id)
    removed, edited, kept = workflow.get(sid, profile.id).scene_objects[:3]
    added_id = uuid4()
    workflow.review(sid, profile.id, ReviewPracticeRequest(
        accepted_object_ids=[edited.id, kept.id],
        added_objects=[AddedPracticeObject(id=added_id, label="lamp", x=0.4, y=0.5)],
        object_attributes={edited.id: {"color": colour}},
        repositioned_objects=[RepositionedPracticeObject(
            id=edited.id, anchor_point={"x": anchor[0], "y": anchor[1]}
        )],
        relations=[SceneObjectRelation(
            subject_scene_object_id=edited.id, relation="beside",
            reference_scene_object_id=added_id,
        )],
    ))
    return sid, removed, edited


def start(games, profile, asset_id, key="game-key-1"):
    return games.start(StartISpyGameRequest(
        language_profile_id=profile.id, media_asset_id=asset_id, idempotency_key=key
    ))


def count(engine, table, sid):
    with engine.connect() as c:
        return c.execute(
            select(func.count()).select_from(table).where(table.c.session_id == sid)
        ).scalar_one()


def test_game_snapshots_the_confirmed_review_under_fresh_ids(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, translator, clues = repos
    asset = upload_asset(engine, owner)
    sid, removed, edited = confirmed_lesson(workflow, profile, asset, "lesson-key-1")
    lesson = workflow.get(sid, profile.id)
    translations = len(translator.payloads)

    gid = start(games, profile, asset).session.id
    game = workflow.get(gid, profile.id)

    assert game.session.mode == "ispy"
    assert game.session.status == "inProgress"
    assert game.session.source_session_id == sid
    assert sorted(o.label for o in game.scene_objects) == sorted(
        o.label for o in lesson.scene_objects
    )
    assert removed.label not in {o.label for o in game.scene_objects}
    lesson_ids = {o.id for o in lesson.scene_objects}
    game_ids = {o.id for o in game.scene_objects}
    assert not lesson_ids & game_ids
    assert all(o.session_id == gid for o in game.scene_objects)
    copy = next(o for o in game.scene_objects if o.label == edited.label)
    assert copy.attributes == {"color": "red"}
    assert (float(copy.anchor_point.x), float(copy.anchor_point.y)) == (0.7, 0.2)
    lamp = next(o for o in game.scene_objects if o.label == "lamp")
    [relation] = game.scene_object_relations
    assert (relation.subject_scene_object_id, relation.relation,
            relation.reference_scene_object_id) == (copy.id, "beside", lamp.id)
    assert relation.id not in {row.id for row in lesson.scene_object_relations}
    assert {o.vocabulary_item_id for o in game.scene_objects} == {
        o.vocabulary_item_id for o in lesson.scene_objects
    }
    # Same languages: the confirmed translation is reused, rekeyed to the snapshot.
    assert len(translator.payloads) == translations
    assert {t.key for t in game.translation_preview.objects} == {str(i) for i in game_ids}
    assert {t.key for t in game.translation_preview.attributes} == {f"{copy.id}:color"}
    assert [t.key for t in game.translation_preview.relationships] == [str(relation.id)]
    assert {o["key"] for o in clues.payloads[-1]["objects"]} == {str(i) for i in game_ids}
    kinds = {task.kind for task in game.tasks}
    assert kinds <= {"ispyRound", "reflection"} and "ispyRound" in kinds
    assert all(t.scene_object_id in game_ids for t in game.tasks if t.scene_object_id)
    # Reload/resume returns the same fixed snapshot and tasks.
    again = workflow.get(gid, profile.id)
    assert [t.id for t in again.tasks] == [t.id for t in game.tasks]
    assert {o.id for o in again.scene_objects} == game_ids


def test_lesson_and_game_on_one_photo_stay_separate(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    asset = upload_asset(engine, owner)
    sid, _, _ = confirmed_lesson(workflow, profile, asset, "lesson-key-2")
    lesson_tasks = [(t.id, t.status) for t in workflow.get(sid, profile.id).tasks]

    gid = start(games, profile, asset).session.id
    assert gid != sid
    assert workflow.create(CreateSessionRequest(
        language_profile_id=profile.id, media_asset_id=asset, idempotency_key="lesson-key-3"
    )).session.id == sid
    assert workflow.active(profile.id).session.id == sid
    assert games.active(profile.id).session.id == gid
    for task in workflow.get(gid, profile.id).tasks:
        workflow.task_action(task.id, "skip", SkipTaskRequest())
    assert workflow.finish(gid, profile.id).status == "completed"

    lesson = workflow.get(sid, profile.id)
    assert lesson.session.status == "inProgress"
    assert [(t.id, t.status) for t in lesson.tasks] == lesson_tasks
    assert count(engine, xp_events, gid) == 0
    assert count(engine, vocabulary_encounters, gid) == 0
    assert games.active(profile.id) is None


def test_duplicate_starts_resume_one_game_and_replay_uses_the_latest_review(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    asset = upload_asset(engine, owner)
    sid, _, edited = confirmed_lesson(workflow, profile, asset, "lesson-key-4")
    first = start(games, profile, asset).session.id
    assert start(games, profile, asset).session.id == first
    assert start(games, profile, asset, "game-key-2").session.id == first
    with pytest.raises(PracticeConflictError):
        start(games, profile, asset, "lesson-key-4")

    # Re-confirming the lesson does not touch the running game.
    lesson = workflow.get(sid, profile.id)
    workflow.review(sid, profile.id, ReviewPracticeRequest(
        accepted_object_ids=[o.id for o in lesson.scene_objects],
        object_attributes={edited.id: {"color": "blue"}},
    ))
    colours = {o.label: o.attributes for o in workflow.get(first, profile.id).scene_objects}
    assert colours[edited.label] == {"color": "red"}

    workflow.finish(first, profile.id, abandon=True)
    replay = workflow.get(start(games, profile, asset, "game-key-3").session.id, profile.id)
    assert replay.session.id != first
    assert {o.label: o.attributes for o in replay.scene_objects}[edited.label] == {
        "color": "blue"
    }
    assert not {t.id for t in replay.tasks} & {
        t.id for t in workflow.get(first, profile.id).tasks
    }


def test_most_recent_confirmation_is_the_source(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    asset = upload_asset(engine, owner)
    older, _, _ = confirmed_lesson(workflow, profile, asset, "lesson-key-5", colour="green")
    workflow.finish(older, profile.id, abandon=True)
    newer, _, _ = confirmed_lesson(workflow, profile, asset, "lesson-key-6", colour="red")
    # Recency comes from the confirmation time, not creation order or IDs.
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.id == older).values(
            scene_confirmed_at=utc_now() + timedelta(minutes=5)
        ))
    game = workflow.get(start(games, profile, asset).session.id, profile.id)
    assert game.session.source_session_id == older
    assert {"color": "green"} in [o.attributes for o in game.scene_objects]
    assert newer != older


def test_unconfirmed_and_foreign_photos_cannot_start_a_game(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    pending = upload_asset(engine, owner)
    sid = workflow.create(CreateSessionRequest(
        language_profile_id=profile.id, media_asset_id=pending, idempotency_key="lesson-key-7"
    )).session.id
    workflow.analyze(sid, profile.id)
    with pytest.raises(PracticeConflictError, match="Confirm"):
        start(games, profile, pending)
    assert CONFIRM_SCENE_FIRST.startswith("Confirm")

    stranger = User(display_name="Stranger", auth_provider_id=f"test-{uuid4()}")
    with engine.begin() as c:
        c.execute(insert(users).values(**stranger.model_dump(by_alias=False)))
    try:
        foreign = upload_asset(engine, stranger)
        with pytest.raises(PracticeNotFoundError):
            start(games, profile, foreign)
    finally:
        with engine.begin() as c:
            c.execute(sessions.delete().where(sessions.c.user_id == stranger.id))


def test_photo_list_pages_own_photos_once_with_playability(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    confirmed = upload_asset(engine, owner)
    confirmed_lesson(workflow, profile, confirmed, "lesson-key-8")
    pending = upload_asset(engine, owner)
    sid = workflow.create(CreateSessionRequest(
        language_profile_id=profile.id, media_asset_id=pending, idempotency_key="lesson-key-9"
    )).session.id
    workflow.analyze(sid, profile.id)
    unused = upload_asset(engine, owner)
    failed = upload_asset(engine, owner)
    reviewed_then_failed = upload_asset(engine, owner)

    def fail(sid):
        with engine.begin() as c:
            c.execute(update(sessions).where(sessions.c.id == sid).values(status="failed"))

    fail(workflow.create(CreateSessionRequest(
        language_profile_id=profile.id, media_asset_id=failed, idempotency_key="lesson-key-9b"
    )).session.id)
    fail(confirmed_lesson(workflow, profile, reviewed_then_failed, "lesson-key-9c")[0])
    start(games, profile, confirmed)

    first = games.photos(limit=2)
    assert len(first.photos) == 2 and first.next_cursor
    second = games.photos(first.next_cursor, limit=2)
    assert second.next_cursor is None
    photos = {p.media_asset.id: p for p in first.photos + second.photos}
    assert set(photos) == {confirmed, pending, reviewed_then_failed}
    assert unused not in photos and failed not in photos
    assert photos[confirmed].playable and photos[confirmed].confirmed_at
    assert photos[reviewed_then_failed].playable
    assert not photos[pending].playable


def test_preloaded_scene_uses_curated_facts_without_a_confirmed_lesson(database, repos):
    _, _, _, client = database
    workflow, games, profile, _, _ = repos
    asset = create_run(client, profile, "preloaded-lesson-key")["mediaAsset"]["id"]
    game = workflow.get(start(games, profile, asset).session.id, profile.id)
    assert game.session.source_session_id is None
    assert game.session.status == "inProgress"
    assert {t.kind for t in game.tasks} <= {"ispyRound", "reflection"}


def test_another_language_retranslates_the_same_confirmed_facts(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, translator, _ = repos
    asset = upload_asset(engine, owner)
    sid, removed, _ = confirmed_lesson(workflow, profile, asset, "lesson-key-10")
    lesson = workflow.get(sid, profile.id)
    profiles = PostgresLanguageProfileRepository(engine)
    with engine.begin() as c:
        c.execute(update(profiles_table()).where(
            profiles_table().c.user_id == owner.id
        ).values(is_active=False))
    french = profiles.create(LanguageProfile(
        user_id=owner.id, source_language_code="en", target_language_code="fr",
        proficiency_level="A1",
    ))
    game = workflow.get(start(games, french, asset).session.id, french.id)
    assert game.session.source_session_id == sid
    assert translator.payloads[-1]["targetLanguage"] == "fr"
    assert sorted(o["source"] for o in translator.payloads[-1]["objects"]) == sorted(
        o.label for o in lesson.scene_objects
    )
    assert removed.label not in {o.label for o in game.scene_objects}
    assert not {o.vocabulary_item_id for o in game.scene_objects} & {
        o.vocabulary_item_id for o in lesson.scene_objects
    }
    assert {t.translation for t in game.translation_preview.objects} == {
        f"fr-{o.label}" for o in lesson.scene_objects
    }


def test_clue_failure_fails_the_game_without_lesson_tasks(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, clues = repos
    asset = upload_asset(engine, owner)
    confirmed_lesson(workflow, profile, asset, "lesson-key-11")
    clues.error = ISpyClueGenerationError("off")
    game = workflow.get(start(games, profile, asset).session.id, profile.id)
    assert game.session.status == "failed"
    assert game.session.failure_code == "taskGenerationFailed"
    assert game.tasks == []
    clues.error = None
    retry = workflow.get(start(games, profile, asset, "game-key-4").session.id, profile.id)
    assert retry.session.status == "inProgress"


def test_games_reject_lesson_review_and_analysis(database, repos):
    engine, owner, _, _ = database
    workflow, games, profile, _, _ = repos
    asset = upload_asset(engine, owner)
    confirmed_lesson(workflow, profile, asset, "lesson-key-12")
    game = workflow.get(start(games, profile, asset).session.id, profile.id)
    with pytest.raises(PracticeConflictError):
        workflow.analyze(game.session.id, profile.id)
    with pytest.raises(PracticeConflictError):
        workflow.review(game.session.id, profile.id, ReviewPracticeRequest(
            accepted_object_ids=[game.scene_objects[0].id]
        ))


def test_ispy_routes(database):
    _, _, profile, client = database
    run = create_run(client, profile, "route-lesson-key")
    response = client.post("/api/v1/ispy/games", json={
        "languageProfileId": str(profile.id),
        "mediaAssetId": run["mediaAsset"]["id"],
        "idempotencyKey": "route-game-key",
    })
    assert response.status_code == 202, response.text
    assert response.json()["session"]["mode"] == "ispy"
    assert client.get("/api/v1/sessions/active").json()["session"]["id"] == run["session"]["id"]
    photos = client.get("/api/v1/ispy/photos")
    assert photos.status_code == 200 and photos.json() == {"photos": [], "nextCursor": None}
    assert client.get("/api/v1/ispy/photos", params={"cursor": "not-a-cursor"}).status_code == 409


def profiles_table():
    from app.repositories.postgres.language_profiles import language_profiles

    return language_profiles


SPANISH_COLOURS = {
    "black": "negro", "blue": "azul", "brown": "marrón", "green": "verde", "grey": "gris",
    "orange": "naranja", "red": "rojo", "white": "blanco", "yellow": "amarillo",
}


class SpanishTranslator(Translator):
    def translate(self, payload, cache_scope=None, **_options):
        self.payloads.append(payload)
        return SceneTranslationResult.model_validate({
            "objects": [
                {**term, "translation": f"es-{term['source']}", "phoneticText": "AH",
                 "gender": "masculine", "article": "el"}
                for term in payload["objects"]
            ],
            "attributes": [
                {**term, "translation": SPANISH_COLOURS[term["source"]], "phoneticText": "AH"}
                for term in payload["attributes"]
            ],
            "relationships": [
                {**term, "translation": f"está cerca de {term['source']}", "phoneticText": "AH"}
                for term in payload["relationships"]
            ],
        })


def test_preloaded_catalog_facts_reference_their_own_items(database):
    engine = database[0]
    with engine.connect() as c:
        rows = c.execute(select(preloaded_scenes.c.slug, preloaded_scenes.c.content)).all()
    assert rows
    for slug, content in rows:
        ids = {item["id"] for item in content["items"]}
        colours = [
            item["attributes"]["color"] for item in content["items"] if item.get("attributes")
        ]
        assert colours and set(colours) <= set(SPANISH_COLOURS), slug
        assert content["relations"], slug
        for row in content["relations"]:
            assert {row["subjectItemId"], row["referenceItemId"]} <= ids, slug
            SceneRelationType(row["relation"])


def test_preloaded_scene_game_gets_describing_rounds(database):
    engine, owner, profile, client = database
    workflow = PostgresWorkflowRepository(
        engine, owner.id, translator=SpanishTranslator(),
        ispy_clue_generator=Clues(), ispy_guess_generator=Guesser(),
    )
    asset = create_run(client, profile, "preloaded-describe-key")["mediaAsset"]["id"]
    game = workflow.get(
        start(PostgresISpyGameRepository(workflow), profile, asset).session.id, profile.id
    )
    assert game.session.source_session_id is None
    assert any(obj.attributes for obj in game.scene_objects)
    assert [t.kind for t in game.tasks].count("reflection") >= 1


def test_latest_attempt_restores_a_graded_clue_choice():
    attempt = TaskAttempt(
        id=uuid4(), session_task_id=uuid4(), attempt_number=1, input_mode="multipleChoice",
        response_payload={"optionId": "taxi"}, is_correct=False,
        feedback={"message": "Not quite."},
    )
    restored = LatestClueAttempt.from_attempt(attempt)
    assert (restored.option_id, restored.is_correct, restored.feedback) == (
        "taxi", False, "Not quite."
    )


def test_latest_attempt_exposes_the_correct_clue_option_only_when_present():
    attempt = TaskAttempt(
        id=uuid4(), session_task_id=uuid4(), attempt_number=2, input_mode="multipleChoice",
        response_payload={"optionId": "wrong"}, is_correct=False,
        feedback={"message": "Not quite. The answer was mesa."},
        evaluation_details={"correctOptionId": "mesa"},
    )
    restored = LatestClueAttempt.from_attempt(attempt)
    assert restored.correct_option_id == "mesa"
    assert restored.model_dump(by_alias=True)["correctOptionId"] == "mesa"

    attempt.evaluation_details = {"retriesLeft": 1}
    restored = LatestClueAttempt.from_attempt(attempt)
    assert restored.correct_option_id is None
    assert "correctOptionId" not in restored.model_dump(by_alias=True)
