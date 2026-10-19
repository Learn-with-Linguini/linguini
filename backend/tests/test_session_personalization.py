"""Returning vocabulary changes order, never scene facts or evaluation keys."""

from copy import deepcopy
from uuid import uuid4

from app.schemas.tasks import SessionTask
from app.services.session_personalization import (
    lesson_history,
    personalization_summary,
    personalize_introduction,
)


def introduction():
    terms = [("cup", "taza"), ("chair", "silla"), ("table", "mesa")]
    return SessionTask.model_validate({
        "sessionId": uuid4(), "phase": "learning", "kind": "vocabularyIntroduction",
        "orderIndex": 0,
        "publicContent": {
            "kind": "vocabularyIntroduction", "title": "Words from your photo",
            "words": [{"learningKey": source, "targetText": target, "translation": source,
                       "partOfSpeech": "noun", "sceneObjectId": uuid4()}
                      for source, target in terms],
            "questions": [{"questionId": f"word-{source}", "prompt": "Choose its meaning.",
                           "options": [{"optionId": "a", "label": source},
                                       {"optionId": "b", "label": "other"}],
                           "correctOptionId": "a"} for source, _target in terms],
        },
        "answerKey": {"correctOptionIds": {f"word-{source}": "a" for source, _ in terms}},
    })


def history():
    return {
        "totals": {"sessionsCompleted": 0},
        "words": [
            {"term": "taza", "source": "cup", "correctCount": 3, "incorrectCount": 0,
             "lastOutcome": "correct", "relevant": False},
            {"term": "mesa", "source": "table", "correctCount": 5, "incorrectCount": 1,
             "lastOutcome": "incorrect", "relevant": False},
            {"term": "perro", "source": "dog", "correctCount": 0, "incorrectCount": 1,
             "lastOutcome": "incorrect", "relevant": True},
        ],
        "grammar": {
            "genderNumberAgreement": {"lastOutcome": "incorrect"},
            "sceneDescription": {"lastOutcome": "incorrect"},
        },
    }


def test_missed_words_then_new_words_then_familiar_words_keep_evaluation_identity():
    original = introduction()
    before = original.model_dump(mode="json")
    reordered = personalize_introduction(original, history())
    assert [word.target_text for word in reordered.public_content.words] == [
        "mesa", "silla", "taza",
    ]
    assert [question.question_id for question in reordered.public_content.questions] == [
        "word-table", "word-chair", "word-cup",
    ]
    assert reordered.id == original.id
    assert reordered.answer_key == original.answer_key
    assert set(word.scene_object_id for word in reordered.public_content.words) == {
        word.scene_object_id for word in original.public_content.words
    }
    assert original.model_dump(mode="json") == before
    for question in reordered.public_content.questions:
        assert question == next(q for q in original.public_content.questions
                                if q.question_id == question.question_id)


def test_summary_includes_only_current_words_and_applicable_observed_focuses():
    result = personalization_summary(history(), introduction(), has_relations=False)
    assert result.model_dump(mode="json", by_alias=True) == {
        "previousSessions": 0,
        "returningWords": [{"word": "taza", "needsReview": False},
                           {"word": "mesa", "needsReview": True}],
        "practiceFocuses": ["genderNumberAgreement"],
    }
    related = personalization_summary(history(), introduction(), has_relations=True)
    assert related.practice_focuses == [
        "genderNumberAgreement", "sceneDescription",
    ]


def test_relevance_is_resolved_after_translation_without_mutating_claim_snapshot():
    snapshot = history()
    before = deepcopy(snapshot)
    resolved = lesson_history(snapshot, introduction())
    assert [word["relevant"] for word in resolved["words"]] == [True, True, False]
    resolved["words"][0]["correctCount"] += 1
    assert snapshot == before


def test_empty_history_preserves_original_plan_and_hides_empty_summary():
    task = introduction()
    assert personalize_introduction(task, None) is task
    assert lesson_history(None, task) is None
    assert personalization_summary(None, task, has_relations=True) is None
    empty = {"totals": {"sessionsCompleted": 9}, "words": [], "grammar": {}}
    assert personalization_summary(empty, task, has_relations=True) is None


def test_exposure_and_journal_use_do_not_imply_recall_or_need_for_review():
    snapshot = {"totals": {"sessionsCompleted": 1}, "words": [{
        "term": "taza", "source": "cup", "seenCount": 12, "journalSelections": 10,
        "assistedJournalMentions": 5, "correctCount": 0, "incorrectCount": 0,
        "lastOutcome": None,
    }], "grammar": {}}
    result = personalization_summary(snapshot, introduction(), has_relations=False)
    assert result.returning_words[0].needs_review is False
    assert result.practice_focuses == []


def test_returning_target_words_match_articles_when_saved_source_wording_differs():
    task = introduction()
    task.public_content.words[-1].target_text = "La mesa"
    snapshot = history()
    snapshot["profile"] = {"targetLanguage": "es", "sourceLanguage": "en"}
    snapshot["words"][1]["source"] = "the table"
    reordered = personalize_introduction(task, snapshot)
    assert reordered.public_content.words[0].target_text == "La mesa"
    assert lesson_history(snapshot, task)["words"][1]["relevant"] is True


def test_shared_source_translation_does_not_transfer_another_target_words_outcome():
    task = introduction()
    task.public_content.words[0].target_text = "vidrio"
    task.public_content.words[0].translation = "glass"
    snapshot = {"totals": {"sessionsCompleted": 1}, "grammar": {}, "words": [
        {"term": "vaso", "source": "glass", "lastOutcome": "incorrect"},
        {"term": "vidrio", "source": "glass", "lastOutcome": "correct"},
    ]}
    result = personalization_summary(snapshot, task, has_relations=False)
    assert result.returning_words[0].word == "vidrio"
    assert result.returning_words[0].needs_review is False
    snapshot["words"].pop()
    assert personalization_summary(snapshot, task, has_relations=False) is None
    assert lesson_history(snapshot, task)["words"][0]["relevant"] is False


def test_same_target_homonym_does_not_inherit_an_unrelated_meanings_errors():
    task = introduction()
    task.public_content.words[0].target_text = "banco"
    task.public_content.words[0].translation = "bench"
    snapshot = {"totals": {"sessionsCompleted": 1}, "grammar": {}, "words": [
        {"term": "banco", "source": "bank", "lastOutcome": "incorrect"},
    ]}
    assert personalization_summary(snapshot, task, has_relations=False) is None
    assert lesson_history(snapshot, task)["words"][0]["relevant"] is False
