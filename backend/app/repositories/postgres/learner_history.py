"""Private, read-only observations from accepted learning history.

This is not a mastery model: recognition answers, exposure and assisted journal
writing remain distinct. All eligible history participates before the model's
small context is selected. No journal prose or submitted answers leave here.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Connection, cast, func, select
from sqlalchemy.dialects.postgresql import JSONPATH

from app.repositories.postgres.journals import journal_revisions, journal_suggestions, journals
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.practice import sessions
from app.repositories.postgres.tasks import session_tasks, task_attempts
from app.repositories.postgres.vocabulary import (
    vocabulary_encounters,
    vocabulary_items,
    vocabulary_translations,
)
from app.schemas.enums import SessionMode

MAX_WORDS = 16
MAX_CONTEXT_BYTES = 6 * 1024
GRAMMAR_FOCUSES = (
    "genderNumberAgreement", "pluralNounForm", "sceneDescription", "chainedDescription",
)
CORRECTION_TYPES = ("grammar", "spelling", "syntax", "vocabulary", "clarity")
READING_TASKS = {"vocabularyIntroduction", "grammarExplanation", "syntaxExplanation"}
_EPOCH = datetime.min.replace(tzinfo=UTC)


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("’", "'").split())


def _without_article(value: str, language: str) -> str:
    value = _normalized(value)
    if language.startswith("en"):
        value = re.sub(r"^(?:the|a|an) ", "", value)
    elif language.startswith("es"):
        value = re.sub(r"^(?:el|la|los|las|un|una|unos|unas) ", "", value)
    elif language.startswith("fr"):
        value = re.sub(r"^(?:(?:le|la|les|un|une|des) |l')", "", value)
    elif language.startswith("de"):
        value = re.sub(r"^(?:der|die|das|den|dem|ein|eine|einen|einem) ", "", value)
    return value


def _safe_term(value) -> str | None:
    """Accept short lexical phrases, excluding identifiers, URLs and free prose."""
    if not isinstance(value, str) or any(character in value for character in "\n\r\t"):
        return None
    value = _normalized(value)
    if not value or len(value) > 64 or len(value.split()) > 8:
        return None
    if not all(character.isalpha() or character in " '-" for character in value):
        return None
    return value if any(character.isalpha() for character in value) else None


def _value(row: dict, snake: str, camel: str):
    return row.get(snake, row.get(camel))


@dataclass
class _Counts:
    correct: int = 0
    incorrect: int = 0
    last: tuple = (_EPOCH, "", "")
    outcome: str | None = None

    def observe(self, result: bool, occurred_at: datetime, event_id, question_id="") -> None:
        self.correct += int(result)
        self.incorrect += int(not result)
        stamp = (occurred_at, str(event_id), str(question_id))
        if stamp > self.last:
            self.last = stamp
            self.outcome = "correct" if result else "incorrect"

    def observe_batch(self, results: list[bool], occurred_at: datetime, event_id) -> None:
        """Keep question counts, but summarize the latest grammar attempt as a whole."""
        if not results:
            return
        self.correct += sum(results)
        self.incorrect += len(results) - sum(results)
        stamp = (occurred_at, str(event_id), "")
        if stamp > self.last:
            self.last = stamp
            self.outcome = "correct" if all(results) else "incorrect"

    def summary(self) -> dict:
        return {
            "correctCount": self.correct,
            "incorrectCount": self.incorrect,
            "lastOutcome": self.outcome,
        }


@dataclass
class _Word(_Counts):
    term: str = ""
    source: str = ""
    seen: set = field(default_factory=set)
    recent: datetime = _EPOCH
    mentions: int = 0
    assisted_mentions: int = 0
    selections: int = 0

    def summary(self, relevant: bool) -> dict:
        return {
            "term": self.term,
            "source": self.source,
            "seenCount": len(self.seen),
            **super().summary(),
            "journalMentions": self.mentions,
            "assistedJournalMentions": self.assisted_mentions,
            "journalSelections": self.selections,
            "relevant": relevant,
        }


def snapshot_learner_history(
    connection: Connection,
    user_id: UUID,
    profile: dict,
    excluded_session_id: UUID,
    scene_labels: list[str],
) -> dict | None:
    """Freeze bounded, profile-isolated evidence using SELECTs only.

    Caller owns transaction/failure handling. No arbitrary last-N session limit:
    older observations count even when their term is omitted from the payload.
    Public exercise answers are visible during recognition, so these counts must
    never be described as unassisted recall or mastery.
    """
    owned_profile = connection.execute(
        select(
            language_profiles.c.source_language_code,
            language_profiles.c.target_language_code,
            language_profiles.c.proficiency_level,
        ).where(language_profiles.c.id == profile["id"], language_profiles.c.user_id == user_id)
    ).mappings().one_or_none()
    if owned_profile is None:
        return None
    source_language = owned_profile["source_language_code"].lower()
    target_language = owned_profile["target_language_code"].lower()
    scope = (
        sessions.c.user_id == user_id,
        sessions.c.language_profile_id == profile["id"],
        sessions.c.mode == SessionMode.LESSON,
        sessions.c.id != excluded_session_id,
    )
    completed = connection.execute(
        select(func.count()).select_from(sessions).where(*scope, sessions.c.status == "completed")
    ).scalar_one()
    words: dict[tuple[str, str], _Word] = {}
    vocabulary_keys: dict[str, tuple[str, str]] = {}

    def word_for(term, source) -> tuple[tuple[str, str], _Word] | None:
        term, source = _safe_term(term), _safe_term(source)
        if term is None or source is None:
            return None
        key = (
            _without_article(term, target_language), _without_article(source, source_language),
        )
        if not all(key):
            return None
        word = words.setdefault(key, _Word(term=key[0], source=key[1]))
        return key, word

    source_text = (
        select(vocabulary_translations.c.translated_text)
        .where(
            vocabulary_translations.c.vocabulary_item_id == vocabulary_items.c.id,
            func.lower(vocabulary_translations.c.source_language_code) == source_language,
        )
        .order_by(vocabulary_translations.c.updated_at, vocabulary_translations.c.id)
        .limit(1).scalar_subquery()
    )
    encounters = connection.execute(
        select(
            vocabulary_items.c.id, vocabulary_items.c.display_text,
            source_text.label("source"), vocabulary_encounters.c.session_id,
            vocabulary_encounters.c.occurred_at,
        )
        .join(vocabulary_encounters, vocabulary_encounters.c.vocabulary_item_id
              == vocabulary_items.c.id)
        .join(sessions, sessions.c.id == vocabulary_encounters.c.session_id)
        .where(
            *scope, vocabulary_encounters.c.user_id == user_id,
            func.lower(vocabulary_items.c.language_code) == target_language,
            vocabulary_encounters.c.outcome.in_(["completed", "correct", "incorrect"]),
        )
        .order_by(vocabulary_encounters.c.occurred_at, vocabulary_encounters.c.id)
    ).mappings()
    for row in encounters:
        if found := word_for(row["display_text"], row["source"]):
            key, word = found
            vocabulary_keys[str(row["id"])] = key
            word.seen.add(row["session_id"])
            word.recent = max(word.recent, row["occurred_at"])

    task_rows = connection.execute(
        select(
            session_tasks.c.id, session_tasks.c.session_id, session_tasks.c.kind,
            session_tasks.c.status, session_tasks.c.vocabulary_item_id,
            session_tasks.c.created_at,
            session_tasks.c.public_content["words"].label("words"),
            session_tasks.c.public_content["target_text"].astext.label("term"),
            session_tasks.c.public_content["translation"].astext.label("source"),
            session_tasks.c.public_content["focus"].astext.label("focus"),
            func.jsonb_path_query_array(
                session_tasks.c.public_content, cast("$.questions[*].question_id", JSONPATH)
            ).label("question_ids"),
            func.jsonb_path_query_array(
                session_tasks.c.public_content, cast("$.questions[*].questionId", JSONPATH)
            ).label("camel_question_ids"),
        )
        .join(sessions, sessions.c.id == session_tasks.c.session_id)
        .where(*scope).order_by(session_tasks.c.created_at, session_tasks.c.id)
    ).mappings()
    tasks = {}
    for row in task_rows:
        task = dict(row)
        task["question_words"] = {}
        task["question_ids"] = set(row["question_ids"] + row["camel_question_ids"])
        if row["kind"] == "vocabularyIntroduction":
            learning_words = row["words"] if isinstance(row["words"], list) else []
            for learned in learning_words:
                if not isinstance(learned, dict):
                    continue
                item_id = _value(learned, "vocabulary_item_id", "vocabularyItemId")
                key = vocabulary_keys.get(str(item_id))
                found = (
                    (key, words[key]) if key else word_for(
                        _value(learned, "target_text", "targetText"), learned.get("translation")
                    )
                )
                if found is None:
                    continue
                key, word = found
                word.seen.add(row["session_id"])
                word.recent = max(word.recent, row["created_at"])
                learning_key = _value(learned, "learning_key", "learningKey") or item_id
                question_id = f"word-{learning_key}"
                if question_id in task["question_ids"]:
                    existing = task["question_words"].get(question_id, key)
                    # Ambiguous legacy learning keys cannot identify a graded word.
                    task["question_words"][question_id] = key if existing == key else None
            if not learning_words and (found := word_for(row["term"], row["source"])):
                key, word = found
                word.seen.add(row["session_id"])
                word.recent = max(word.recent, row["created_at"])
                task["legacy_word"] = key
        tasks[row["id"]] = task

    grammar = {focus: _Counts() for focus in GRAMMAR_FOCUSES}
    graded_attempts = 0
    attempted_tasks = set()
    attempts = connection.execute(
        select(
            task_attempts.c.id, task_attempts.c.session_task_id,
            task_attempts.c.created_at, task_attempts.c.is_correct,
            task_attempts.c.evaluation_details["questionResults"].label("results"),
        )
        .join(session_tasks, session_tasks.c.id == task_attempts.c.session_task_id)
        .join(sessions, sessions.c.id == session_tasks.c.session_id)
        .where(*scope).order_by(task_attempts.c.created_at, task_attempts.c.id)
    ).mappings()
    for attempt in attempts:
        task = tasks[attempt["session_task_id"]]
        attempted_tasks.add(task["id"])
        if type(attempt["is_correct"]) is bool:
            graded_attempts += 1
        results = attempt["results"]
        if isinstance(results, dict):
            valid_results = []
            for question_id, result in results.items():
                if type(result) is not bool or question_id not in task["question_ids"]:
                    continue
                valid_results.append(result)
                if key := task["question_words"].get(question_id):
                    word = words[key]
                    word.observe(result, attempt["created_at"], attempt["id"], question_id)
                    word.recent = max(word.recent, attempt["created_at"])
            if task["kind"] == "grammarLesson" and task["focus"] in grammar:
                grammar[task["focus"]].observe_batch(
                    valid_results, attempt["created_at"], attempt["id"],
                )
        if type(attempt["is_correct"]) is bool and (
            key := task.get("legacy_word") or (
                vocabulary_keys.get(str(task["vocabulary_item_id"]))
                if task["kind"] == "ispyRound" else None
            )
        ):
            word = words[key]
            word.observe(attempt["is_correct"], attempt["created_at"], attempt["id"])
            word.recent = max(word.recent, attempt["created_at"])

    reading = sum(
        task["status"] == "completed" and task["kind"] in READING_TASKS
        and not (task["kind"] == "vocabularyIntroduction" and task["words"])
        and task["id"] not in attempted_tasks for task in tasks.values()
    )
    journal_scope = (
        journals.c.user_id == user_id, journals.c.language_profile_id == profile["id"],
        journals.c.status == "completed",
    )
    current_journals = connection.execute(
        select(
            journals.c.selected_words, journals.c.updated_at,
            journal_revisions.c.content, journal_revisions.c.created_by,
        )
        .join(journal_revisions, (journal_revisions.c.id == journals.c.current_revision_id)
              & (journal_revisions.c.journal_id == journals.c.id))
        .where(*journal_scope).order_by(journals.c.id)
    ).mappings()
    journal_count = 0
    phrase_patterns = {
        word.term: re.compile(r"(?<!\w)" + re.escape(word.term) + r"(?!\w)")
        for word in words.values() if not word.term.isalpha()
    }
    for journal in current_journals:
        journal_count += 1
        selected = {
            _without_article(label, target_language)
            for label in journal["selected_words"] if isinstance(label, str)
        } if isinstance(journal["selected_words"], list) else set()
        content = _normalized(journal["content"])
        content_terms = set(re.findall(r"\w+", content))
        for word in words.values():
            used = (
                word.term in content_terms if word.term.isalpha()
                else bool(phrase_patterns[word.term].search(content))
            )
            if used:
                if journal["created_by"] == "user":
                    word.mentions += 1
                else:
                    word.assisted_mentions += 1
            if word.term in selected:
                word.selections += 1
            if used or word.term in selected:
                word.recent = max(word.recent, journal["updated_at"])
    corrections = {category: 0 for category in CORRECTION_TYPES}
    correction_rows = connection.execute(
        select(journal_suggestions.c.suggestion_type, func.count().label("count"))
        .join(journals, journals.c.id == journal_suggestions.c.journal_id)
        .join(journal_revisions, (journal_revisions.c.id == journals.c.current_revision_id)
              & (journal_revisions.c.journal_id == journals.c.id))
        .where(*journal_scope, journal_suggestions.c.status == "accepted")
        .group_by(journal_suggestions.c.suggestion_type)
    ).mappings()
    for row in correction_rows:
        if row["suggestion_type"] in corrections:
            corrections[row["suggestion_type"]] = row["count"]
    if not words and not graded_attempts and not reading and not journal_count:
        return None

    labels = {
        _without_article(label, language)
        for label in scene_labels for language in (source_language, target_language)
    }
    ranked = sorted(words.values(), key=lambda word: (
        -(word.term in labels or word.source in labels),
        -(word.outcome == "incorrect"),
        -word.last[0].timestamp() if word.outcome == "incorrect" else 0,
        -word.recent.timestamp(), word.term, word.source,
    ))
    context = {
        "version": 1,
        "profile": {
            "sourceLanguage": source_language, "targetLanguage": target_language,
            "proficiencyLevel": owned_profile["proficiency_level"],
        },
        "totals": {
            "sessionsCompleted": completed, "gradedAttempts": graded_attempts,
            "readingTasksCompleted": reading, "journalsCompleted": journal_count,
        },
        "words": [
            word.summary(word.term in labels or word.source in labels)
            for word in ranked[:MAX_WORDS]
        ],
        "grammar": {focus: counts.summary() for focus, counts in grammar.items()},
        "journal": {"acceptedCorrections": corrections},
    }
    while len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        context["words"].pop()
    return context
