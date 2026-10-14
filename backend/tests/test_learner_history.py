"""Real PostgreSQL history, privacy and evidence-boundary checks."""

import json
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, select, text, update

from app.database import create_database_engine
from app.repositories.postgres.journals import journal_revisions, journal_suggestions, journals
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.learner_history import MAX_CONTEXT_BYTES, snapshot_learner_history
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.users import users
from app.repositories.postgres.vocabulary import (
    user_vocabulary_progress,
    vocabulary_encounters,
    vocabulary_items,
    vocabulary_translations,
)
from app.schemas.base import utc_now
from app.schemas.enums import SessionMode
from app.schemas.media import MediaAsset
from app.schemas.users import LanguageProfile, User
from app.schemas.vocabulary import UserVocabularyProgress, VocabularyItem, VocabularyTranslation


class History:
    def __init__(self, connection):
        self.connection = connection
        self.now = utc_now()
        self.owner = User(display_name="Private person", auth_provider_id=f"history-{uuid4()}")
        connection.execute(insert(users).values(**self.owner.model_dump(by_alias=False)))
        self.profile = self.add_profile(self.owner.id)
        asset = MediaAsset(
            owner_user_id=self.owner.id, media_type="image", source="userUpload",
            storage_key=f"test/{uuid4()}", mime_type="image/jpeg",
        )
        connection.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
        self.asset_id = asset.id
        self.journal_number = 0
        self.attempt_numbers = {}
        self.task_numbers = {}

    def add_profile(self, user_id, source="en", target="es"):
        profile = LanguageProfile(
            user_id=user_id, source_language_code=source, target_language_code=target,
            proficiency_level="A1", is_active=False,
        )
        self.connection.execute(
            insert(language_profiles).values(**profile.model_dump(by_alias=False))
        )
        return profile

    def session(self, profile=None, status="completed", mode=SessionMode.LESSON):
        profile = profile or self.profile
        asset_id = self.asset_id
        if profile.user_id != self.owner.id:
            asset = MediaAsset(
                owner_user_id=profile.user_id, media_type="image", source="userUpload",
                storage_key=f"test/{uuid4()}", mime_type="image/jpeg",
            )
            self.connection.execute(insert(media_assets).values(**asset.model_dump(by_alias=False)))
            asset_id = asset.id
        session_id = uuid4()
        self.connection.execute(insert(sessions).values(
            id=session_id, user_id=profile.user_id, language_profile_id=profile.id,
            scene_media_asset_id=asset_id, status=status, mode=mode,
            started_at=self.now, completed_at=self.now if status == "completed" else None,
            abandoned_at=self.now if status == "abandoned" else None,
        ))
        return session_id

    def task(self, session_id, kind, content, status="completed", occurred_at=None, item_id=None):
        task_id = uuid4()
        order = self.task_numbers.get(session_id, 0)
        self.task_numbers[session_id] = order + 1
        self.connection.execute(insert(session_tasks).values(
            id=task_id, session_id=session_id,
            phase="ispy" if kind == "ispyRound" else "learning", kind=kind, order_index=order,
            status=status, public_content={"kind": kind, **content}, vocabulary_item_id=item_id,
            completed_at=(occurred_at or self.now) if status == "completed" else None,
            skipped_at=(occurred_at or self.now) if status == "skipped" else None,
            created_at=occurred_at or self.now, updated_at=occurred_at or self.now,
        ))
        return task_id

    def attempt(self, task_id, results=None, correct=False, occurred_at=None, private=None,
                input_mode="vocabularyReview"):
        attempt_id = uuid4()
        attempt_number = self.attempt_numbers.get(task_id, 0) + 1
        self.attempt_numbers[task_id] = attempt_number
        self.connection.execute(insert(task_attempts).values(
            id=attempt_id, session_task_id=task_id, attempt_number=attempt_number,
            input_mode=input_mode,
            response_payload=private or {"answers": {"private": "never sent to the model"}},
            is_correct=correct, created_at=occurred_at or self.now,
            updated_at=occurred_at or self.now,
            evaluation_details={"questionResults": results} if results is not None else None,
        ))
        return attempt_id

    def word(self, term, source, owner=None, language="es"):
        owner = owner or self.owner.id
        word = VocabularyItem(
            language_code=language, lemma=term, display_text=term, part_of_speech="noun",
        )
        self.connection.execute(insert(vocabulary_items).values(**word.model_dump(by_alias=False)))
        translation = VocabularyTranslation(
            vocabulary_item_id=word.id, source_language_code="en", translated_text=source,
        )
        self.connection.execute(insert(vocabulary_translations).values(
            **translation.model_dump(by_alias=False)
        ))
        progress = UserVocabularyProgress(user_id=owner, vocabulary_item_id=word.id)
        self.connection.execute(insert(user_vocabulary_progress).values(
            **progress.model_dump(by_alias=False)
        ))
        return word.id

    def encounter(self, session_id, task_id, item_id, outcome="completed", occurred_at=None):
        self.connection.execute(insert(vocabulary_encounters).values(
            id=uuid4(), user_id=self.owner.id, vocabulary_item_id=item_id,
            session_id=session_id, session_task_id=task_id, encounter_type="introduced",
            outcome=outcome, occurred_at=occurred_at or self.now,
            created_at=self.now, updated_at=self.now,
        ))

    def learn(self, session_id, entries, results=None, occurred_at=None):
        content = {
            "words": entries,
            "questions": [{"question_id": f"word-{entry['learning_key']}"} for entry in entries],
        }
        task_id = self.task(
            session_id, "vocabularyIntroduction", content, occurred_at=occurred_at,
        )
        if results is not None:
            self.attempt(task_id, results, occurred_at=occurred_at)
        return task_id

    def journal(self, content, selected=None, creator="user", status="completed", profile=None):
        profile = profile or self.profile
        self.journal_number += 1
        journal_id, revision_id = uuid4(), uuid4()
        self.connection.execute(insert(journals).values(
            id=journal_id, user_id=profile.user_id, language_profile_id=profile.id,
            local_date=date(2020, 1, 1) + timedelta(days=self.journal_number),
            timezone="UTC", title="Private title", selected_words=selected or [], status=status,
            current_revision_id=revision_id,
            completed_at=self.now if status == "completed" else None,
            created_at=self.now, updated_at=self.now,
        ))
        self.connection.execute(insert(journal_revisions).values(
            id=revision_id, journal_id=journal_id, revision_number=1, content=content,
            created_by=creator, created_at=self.now, updated_at=self.now,
        ))
        return journal_id, revision_id

    def snapshot(self, excluded=None, labels=None, profile=None, user_id=None):
        return snapshot_learner_history(
            self.connection, user_id or self.owner.id,
            (profile or self.profile).model_dump(by_alias=False),
            excluded or uuid4(), labels or [],
        )


@pytest.fixture
def history(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated disposable PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    if os.getenv("TEST_DATABASE_SCHEMA"):
        engine = engine.execution_options(
            schema_translate_map={"public": os.environ["TEST_DATABASE_SCHEMA"]}
        )
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield History(connection)
        finally:
            transaction.rollback()
    engine.dispose()


def entry(term, source, key=None, item_id=None):
    return {
        "learning_key": key or str(item_id or uuid4()), "target_text": term,
        "translation": source, "vocabulary_item_id": str(item_id) if item_id else None,
    }


def words_by_term(snapshot):
    return {word["term"]: word for word in snapshot["words"]}


def test_cold_start_ignores_manual_mastery_drafts_skips_and_current_session(history):
    assert history.snapshot() is None
    item = history.word("taza", "cup")
    history.connection.execute(update(user_vocabulary_progress).values(
        status="mastered", mastery_score=1, exposure_count=500, correct_attempt_count=499,
    ).where(user_vocabulary_progress.c.user_id == history.owner.id))
    history.journal("taza", selected=["taza"], status="draft")
    sid = history.session()
    history.task(sid, "grammarExplanation", {}, status="skipped")
    assert history.snapshot() is None
    current = history.session()
    history.learn(current, [entry("la taza", "cup", item_id=item)])
    assert history.snapshot(excluded=current) is None


def test_standalone_game_observations_never_enter_lesson_history(history):
    game = history.session(mode=SessionMode.ISPY)
    hidden_word = history.word("secreto", "secret")
    round_id = history.task(game, "ispyRound", {
        "prompt": "Choose the described object", "options": ["hidden", "other"],
    }, item_id=hidden_word)
    history.encounter(game, round_id, hidden_word, outcome="correct")
    history.attempt(round_id, correct=True, input_mode="multipleChoice")
    assert history.snapshot() is None

    lesson = history.session()
    cup = history.word("taza", "cup")
    introduction = history.learn(lesson, [entry("la taza", "cup", item_id=cup)], {
        f"word-{cup}": False,
    })
    history.encounter(lesson, introduction, cup)
    snapshot = history.snapshot()
    assert snapshot["totals"]["sessionsCompleted"] == 1
    assert snapshot["totals"]["gradedAttempts"] == 1
    assert [word["term"] for word in snapshot["words"]] == ["taza"]
    assert snapshot["words"][0]["incorrectCount"] == 1
    assert snapshot == history.snapshot(excluded=game)
    assert history.snapshot(excluded=lesson) is None


def test_exact_word_results_include_adjectives_and_prepositions_without_group_scoring(history):
    cup = history.word("taza", "cup")
    plate = history.word("plato", "plate")
    entries = [
        entry("la taza", "cup", item_id=cup), entry("el plato", "plate", item_id=plate),
        entry("rojo", "red", "attribute:color"), entry("encima de", "on", "relationship:on"),
    ]
    sid = history.session(status="abandoned")
    task = history.learn(sid, entries, {
        f"word-{cup}": True, f"word-{plate}": False,
        "word-attribute:color": False, "word-relationship:on": True,
        "unknown": False,
    })
    # Legacy grouped encounters record the whole attempt's incorrect outcome.
    for item in (cup, plate):
        history.encounter(sid, task, item, outcome="incorrect")
    snapshot = history.snapshot(labels=["Cup"])
    words = words_by_term(snapshot)
    assert list(words)[0] == "taza"
    assert words["taza"]["relevant"] is True
    assert words["taza"]["seenCount"] == 1
    assert (words["taza"]["correctCount"], words["taza"]["incorrectCount"]) == (1, 0)
    assert words["plato"]["incorrectCount"] == 1
    assert words["rojo"]["lastOutcome"] == "incorrect"
    assert words["encima de"]["correctCount"] == 1
    assert snapshot["totals"]["sessionsCompleted"] == 0
    assert snapshot["totals"]["gradedAttempts"] == 1


def test_grammar_counts_only_saved_questions_and_real_booleans(history):
    sid = history.session()
    task = history.task(sid, "grammarLesson", {
        "focus": "genderNumberAgreement",
        "questions": [{"question_id": question_id} for question_id in ("a", "b", "c")],
    })
    history.attempt(task, {"a": True, "b": False, "c": "false", "injected": False})
    history.attempt(task, {"a": True}, correct=True, occurred_at=history.now + timedelta(seconds=1))
    unknown = history.task(sid, "grammarLesson", {
        "focus": "imaginaryFocus", "questions": [{"question_id": "a"}],
    })
    history.attempt(unknown, {"a": False})
    reading = history.task(sid, "grammarExplanation", {})
    assert reading
    snapshot = history.snapshot()
    assert snapshot["grammar"]["genderNumberAgreement"] == {
        "correctCount": 2, "incorrectCount": 1, "lastOutcome": "correct",
    }
    assert snapshot["grammar"]["pluralNounForm"] == {
        "correctCount": 0, "incorrectCount": 0, "lastOutcome": None,
    }
    assert snapshot["totals"] == {
        "sessionsCompleted": 1, "gradedAttempts": 3,
        "readingTasksCompleted": 1, "journalsCompleted": 0,
    }


@pytest.mark.parametrize("wrong_id,right_id", [("a", "z"), ("z", "a"), ("q-42", "q-1")])
def test_latest_grammar_batch_outcome_does_not_depend_on_question_ids(history, wrong_id, right_id):
    task = history.task(history.session(), "grammarLesson", {
        "focus": "pluralNounForm",
        "questions": [
            {"question_id": question_id} for question_id in (wrong_id, right_id, "ungraded")
        ],
    })
    history.attempt(task, {
        wrong_id: False, right_id: True, "ungraded": "false", "unknown": False,
    })
    assert history.snapshot()["grammar"]["pluralNounForm"] == {
        "correctCount": 1, "incorrectCount": 1, "lastOutcome": "incorrect",
    }
    # A newer batch without valid saved-question grading provides no outcome.
    history.attempt(task, {"ungraded": "true", "unknown": False},
                    occurred_at=history.now + timedelta(seconds=1))
    assert history.snapshot()["grammar"]["pluralNounForm"] == {
        "correctCount": 1, "incorrectCount": 1, "lastOutcome": "incorrect",
    }
    history.attempt(task, {wrong_id: True, right_id: True}, correct=True,
                    occurred_at=history.now + timedelta(seconds=2))
    assert history.snapshot()["grammar"]["pluralNounForm"] == {
        "correctCount": 3, "incorrectCount": 1, "lastOutcome": "correct",
    }


def test_journals_use_current_completed_content_and_separate_assisted_selection(history):
    sid = history.session()
    history.learn(sid, [entry("taza", "cup"), entry("plato", "plate"), entry("rojo", "red")])
    private = f"Private person https://private.invalid {uuid4()} says taza. tazador platos"
    jid, rid = history.journal("plato", selected=["el plato"])
    current = uuid4()
    history.connection.execute(insert(journal_revisions).values(
        id=current, journal_id=jid, revision_number=2, content=private, created_by="user",
        created_at=history.now, updated_at=history.now,
    ))
    history.connection.execute(update(journals).where(journals.c.id == jid).values(
        current_revision_id=current,
    ))
    history.journal("taza", status="draft")
    history.journal("rojo", creator="merged")
    for status in ("accepted", "pending", "rejected"):
        history.connection.execute(insert(journal_suggestions).values(
            id=uuid4(), journal_id=jid, base_revision_id=rid, suggestion_type="grammar",
            start_offset=0, end_offset=1, original_text="p", suggested_text="P",
            explanation="Private explanation", status=status,
            created_at=history.now, updated_at=history.now,
        ))
    snapshot = history.snapshot()
    words = words_by_term(snapshot)
    assert words["taza"]["journalMentions"] == 1
    assert words["plato"]["journalMentions"] == 0
    assert words["plato"]["journalSelections"] == 1
    assert words["plato"]["correctCount"] == 0
    assert words["rojo"]["assistedJournalMentions"] == 1
    assert words["rojo"]["journalMentions"] == 0
    assert snapshot["journal"]["acceptedCorrections"]["grammar"] == 1
    assert snapshot["totals"]["journalsCompleted"] == 2
    encoded = json.dumps(snapshot)
    forbidden_values = (
        "Private person", "private.invalid", "Private explanation", str(jid), str(rid),
    )
    for forbidden in forbidden_values:
        assert forbidden not in encoded


def test_owner_and_same_target_different_source_profile_are_isolated(history):
    other_profile = history.add_profile(history.owner.id, source="fr", target="es")
    history.learn(history.session(other_profile), [entry("secreto", "secret")])
    history.journal("secreto", selected=["secreto"], profile=other_profile)
    assert history.snapshot() is None
    assert history.snapshot(profile=other_profile)["words"][0]["term"] == "secreto"
    assert history.snapshot(user_id=uuid4(), profile=other_profile) is None
    assert history.snapshot() is None


def test_all_old_history_counts_and_context_selection_is_bounded_and_deterministic(history):
    old = history.now - timedelta(days=365)
    for index in range(25):
        term = "語" * 60 + chr(ord("a") + index)
        source = "漢" * 60 + chr(ord("a") + index)
        sid = history.session()
        learned = entry(term, source, key=f"word{index}")
        history.learn(sid, [learned], {f"word-word{index}": index != 0}, occurred_at=old)
    relevant = "語" * 60 + "y"
    snapshot = history.snapshot(labels=[relevant])
    assert snapshot["totals"]["sessionsCompleted"] == 25
    assert snapshot["totals"]["gradedAttempts"] == 25
    assert len(snapshot["words"]) <= 16
    assert snapshot["words"][0]["term"] == relevant
    assert snapshot["words"][1]["lastOutcome"] == "incorrect"
    assert len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) <= MAX_CONTEXT_BYTES
    assert snapshot == history.snapshot(labels=[relevant])


def test_snapshot_uses_selects_only_and_never_reads_submitted_answers(history):
    sid = history.session()
    task = history.learn(sid, [entry("taza", "cup", "cup")])
    history.attempt(task, {"word-cup": True}, correct=True, private={
        "text": "Private person https://secret.invalid", "name": "Private person",
    })
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(history.connection, "before_cursor_execute", capture)
    try:
        result = history.snapshot()
    finally:
        event.remove(history.connection, "before_cursor_execute", capture)
    assert result["words"][0]["correctCount"] == 1
    assert statements and all(statement.lstrip().startswith("SELECT") for statement in statements)
    assert all("response_payload" not in statement for statement in statements)
    assert all("answer_key" not in statement for statement in statements)
    assert "secret.invalid" not in json.dumps(result)
    persisted = history.connection.execute(
        select(task_attempts.c.response_payload).where(task_attempts.c.session_task_id == task)
    ).scalar_one()
    assert persisted["name"] == "Private person"


@pytest.mark.parametrize("term", ["https://secret.invalid", str(uuid4()), "somebody@example.com"])
def test_nonlexical_terms_do_not_enter_model_context(history, term):
    history.learn(history.session(), [entry(term, "cup")])
    assert history.snapshot() is None


def test_existing_history_can_be_read_in_read_only_transaction(history):
    history.learn(history.session(), [entry("taza", "cup")])
    history.connection.execute(text("SET LOCAL transaction_read_only = on"))
    assert history.snapshot()["words"][0]["term"] == "taza"


def test_repeated_sessions_keep_all_results_and_exclude_current_exposure(history):
    cup = history.word("taza", "cup")
    old = history.now - timedelta(days=365)
    for result, when in ((False, old), (True, history.now)):
        sid = history.session()
        task = history.learn(
            sid, [entry("la taza", "cup", item_id=cup)],
            {f"word-{cup}": result}, occurred_at=when,
        )
        history.encounter(sid, task, cup, occurred_at=when)
    current = history.session()
    history.learn(current, [entry("la taza", "cup", item_id=cup)])
    snapshot = history.snapshot(excluded=current)
    word = snapshot["words"][0]
    assert word["seenCount"] == 2
    assert (word["correctCount"], word["incorrectCount"], word["lastOutcome"]) == (1, 1, "correct")
    assert snapshot["totals"]["sessionsCompleted"] == 2


def test_foreign_owner_history_and_profile_cannot_leak(history):
    stranger = User(display_name="Stranger", auth_provider_id=f"history-{uuid4()}")
    history.connection.execute(insert(users).values(**stranger.model_dump(by_alias=False)))
    foreign = history.add_profile(stranger.id)
    history.learn(history.session(foreign), [entry("secreto", "secret")])
    history.journal("secreto", selected=["secreto"], profile=foreign)
    history.learn(history.session(), [entry("taza", "cup")])
    assert list(words_by_term(history.snapshot())) == ["taza"]
    assert history.snapshot(profile=foreign) is None


def test_french_elision_and_journal_phrase_boundaries_are_conservative(history):
    french = history.add_profile(history.owner.id, target="fr")
    history.learn(history.session(french), [
        entry("l’homme", "man"), entry("à côté de", "next to"), entry("café", "coffee"),
    ])
    history.journal("L'homme est à côté de cafés.", profile=french)
    words = words_by_term(history.snapshot(profile=french, labels=["man"]))
    assert words["homme"]["journalMentions"] == 1
    assert words["à côté de"]["journalMentions"] == 1
    assert words["café"]["journalMentions"] == 0


def test_grouped_aggregate_and_ambiguous_keys_do_not_become_word_accuracy(history):
    sid = history.session()
    task = history.learn(sid, [entry("taza", "cup", "shared"), entry("plato", "plate", "shared")])
    history.attempt(task, {"word-shared": True}, correct=True)
    words = words_by_term(history.snapshot())
    assert all(word["correctCount"] == word["incorrectCount"] == 0 for word in words.values())
    other = history.learn(history.session(), [entry("rojo", "red", "red")])
    history.attempt(other, correct=False)
    assert words_by_term(history.snapshot())["rojo"]["incorrectCount"] == 0


@pytest.mark.parametrize("source_language,term,source,with_article", [
    ("en", "mesa", "table", "the table"),
    ("en", "mesa", "table", "a table"),
    ("en", "objeto", "object", "an object"),
    ("es", "table", "mesa", "la mesa"),
    ("fr", "mesa", "table", "la table"),
    ("fr", "hombre", "homme", "l’homme"),
])
def test_source_articles_merge_concept_counts_and_latest_outcome(
    history, source_language, term, source, with_article,
):
    profile = history.profile if source_language == "en" else history.add_profile(
        history.owner.id, source=source_language, target="fr" if source_language == "es" else "es",
    )
    old = history.now - timedelta(days=90)
    history.learn(
        history.session(profile), [entry(term, source, "old")],
        {"word-old": False}, occurred_at=old,
    )
    history.learn(
        history.session(profile), [entry(term, with_article, "new")],
        {"word-new": True}, occurred_at=history.now,
    )
    snapshot = history.snapshot(profile=profile, labels=[with_article])
    assert len(snapshot["words"]) == 1
    word = snapshot["words"][0]
    assert word["term"] == term and word["source"] == source
    assert word["seenCount"] == 2
    assert word["correctCount"] == word["incorrectCount"] == 1
    assert word["lastOutcome"] == "correct"
    assert word["relevant"] is True


def test_article_normalization_preserves_distinct_meanings(history):
    history.learn(
        history.session(), [entry("el banco", "a bank", "bank")],
        {"word-bank": False}, occurred_at=history.now - timedelta(days=1),
    )
    history.learn(
        history.session(), [entry("banco", "the bench", "bench")],
        {"word-bench": True}, occurred_at=history.now,
    )
    words = {(word["term"], word["source"]): word for word in history.snapshot()["words"]}
    assert set(words) == {("banco", "bank"), ("banco", "bench")}
    assert words[("banco", "bank")]["lastOutcome"] == "incorrect"
    assert words[("banco", "bank")]["correctCount"] == 0
    assert words[("banco", "bench")]["lastOutcome"] == "correct"
    assert words[("banco", "bench")]["incorrectCount"] == 0
