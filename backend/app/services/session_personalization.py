"""Use prior observations to revisit current vocabulary, without declaring mastery."""

import re
import unicodedata
from copy import deepcopy

from app.schemas.sessions import ReturningPracticeWord, SessionPersonalization

GRAMMAR_FOCUSES = (
    "genderNumberAgreement", "pluralNounForm", "sceneDescription", "chainedDescription",
)


def _normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().replace("’", "'").split())


def _lexical_term(value, language):
    term = _normalized(value)
    if language.startswith("en"):
        return re.sub(r"^(?:the|a|an) ", "", term)
    if language.startswith("es"):
        return re.sub(r"^(?:el|la|los|las|un|una|unos|unas) ", "", term)
    if language.startswith("fr"):
        return re.sub(r"^(?:(?:le|la|les|un|une|des) |l')", "", term)
    return term


def _matches(word, item, history):
    profile = (history or {}).get("profile", {})
    return (
        _lexical_term(word.target_text, profile.get("targetLanguage", ""))
        == _lexical_term(item["term"], profile.get("targetLanguage", ""))
        and _lexical_term(word.translation, profile.get("sourceLanguage", ""))
        == _lexical_term(item["source"], profile.get("sourceLanguage", ""))
    )


def _needs_review(observation):
    return observation.get("lastOutcome") == "incorrect" or (
        observation.get("incorrectCount", 0) > observation.get("correctCount", 0)
    )


def _observation(word, history):
    return next((item for item in (history or {}).get("words", [])
                 if _matches(word, item, history)), None)


def personalize_introduction(task, history):
    """Review previously missed words first; retain IDs, answer keys and scene facts."""
    if not history or not getattr(task.public_content, "words", None):
        return task

    def priority(word):
        observation = _observation(word, history)
        return 0 if observation and _needs_review(observation) else 2 if observation else 1

    content = task.public_content
    words = sorted(content.words, key=priority)
    by_question = {f"word-{word.learning_key}": index for index, word in enumerate(words)}
    questions = sorted(content.questions, key=lambda question: by_question.get(
        question.question_id, len(words),
    ))
    return task.model_copy(update={
        "public_content": content.model_copy(update={"words": words, "questions": questions}),
    })


def lesson_history(history, introduction):
    """Resolve returning vocabulary after translation, preserving the frozen history."""
    if not history:
        return None
    result = deepcopy(history)
    words = getattr(introduction.public_content, "words", [])
    for item in result["words"]:
        item["relevant"] = any(
            _matches(word, item, history)
            for word in words
        )
    return result


def personalization_summary(history, introduction, *, has_relations):
    if not history:
        return None
    returning, seen = [], set()
    for word in getattr(introduction.public_content, "words", []):
        observation = _observation(word, history)
        if observation and _normalized(word.target_text) not in seen:
            seen.add(_normalized(word.target_text))
            returning.append(ReturningPracticeWord(
                word=word.target_text, needs_review=_needs_review(observation),
            ))
    focuses = [focus for focus in GRAMMAR_FOCUSES
               if (has_relations or focus != "sceneDescription")
               and _needs_review(history.get("grammar", {}).get(focus, {}))]
    if not returning and not focuses:
        return None
    return SessionPersonalization(
        previous_sessions=history["totals"]["sessionsCompleted"],
        returning_words=returning[:6], practice_focuses=focuses,
    )
