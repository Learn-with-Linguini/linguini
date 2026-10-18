"""Structured per-question results for tasks with question evaluation metadata."""

import re
from collections import Counter

from app.missions import get_mission
from app.schemas.tasks import QuestionOutcome, QuestionReviewDetails, SessionTask


def normalize_answer(value):
    # French spaces its final "?"/"!", which built answers may omit.
    return " ".join(value.casefold().strip().split()).rstrip(".!?\u3002").rstrip()


# Supports each interaction can offer; a word bank is part of every sentence builder.
_OFFERED_SUPPORTS = {
    "multipleChoice": {"translation", "audio"},
    "sentenceBuilding": {"translation", "audio", "wordBank"},
}
_BUILT_IN_SUPPORTS = {"sentenceBuilding": ["wordBank"]}


def _interaction(question):
    return getattr(question, "interaction_type", "multipleChoice")


def offered_supports(question):
    return _OFFERED_SUPPORTS[_interaction(question)]


def _default_evidence(question):
    """Evidence follows the interaction, never a client claim of independence."""
    if _interaction(question) == "sentenceBuilding":
        return "construction"
    return "recognition"


def word_results(task, question_results):
    """Each word's result from only the graded questions that assess it."""
    results = {}
    for evaluation in task.answer_key.question_evaluations:
        correct = question_results.get(evaluation.question_id)
        if correct is None:
            continue
        for vocabulary_item_id in evaluation.vocabulary_item_ids:
            results[vocabulary_item_id] = results.get(vocabulary_item_id, True) and correct
    return results


def _sentence_building_explanation(answer, correction, explanation):
    answer_tokens = re.findall(r"[\w'’-]+", answer or "")
    correction_tokens = re.findall(r"[\w'’-]+", correction)
    folded_answer = [token.casefold() for token in answer_tokens]
    folded_correction = [token.casefold() for token in correction_tokens]

    def unmatched(tokens, counts):
        remaining = counts.copy()
        result = []
        for token in tokens:
            folded = token.casefold()
            if remaining[folded]:
                remaining[folded] -= 1
            else:
                result.append(token)
        return result

    def common(tokens, counts):
        remaining = counts.copy()
        result = []
        for token in tokens:
            folded = token.casefold()
            if remaining[folded]:
                remaining[folded] -= 1
                result.append(token)
        return result

    extra = unmatched(answer_tokens, Counter(folded_correction))
    missing = unmatched(correction_tokens, Counter(folded_answer))

    answer_common = common(answer_tokens, Counter(folded_correction))
    correction_common = common(correction_tokens, Counter(folded_answer))
    order_wrong = (
        [token.casefold() for token in answer_common]
        != [token.casefold() for token in correction_common]
    )

    if extra and missing:
        message = (
            f"“{' '.join(extra)}” doesn't belong here; the sentence needs "
            f"“{' '.join(missing)}”."
        )
    elif extra:
        message = f"“{' '.join(extra)}” doesn't belong in this sentence."
    elif missing:
        message = f"You left out “{' '.join(missing)}”."
    elif order_wrong:
        message = "You have the right words in the wrong order."
        return f"{message} {explanation}" if explanation else message
    else:
        return explanation

    if order_wrong and explanation:
        message += f" {explanation}"
    return message


def _mistakes(evaluation, answer, question):
    """Rules naming this answer; rules without answers apply only when none does."""
    given = normalize_answer(answer or "")
    specific = [
        rule for rule in evaluation.corrections
        if given in {normalize_answer(item) for item in rule.answers}
    ]
    rules = specific or [rule for rule in evaluation.corrections if not rule.answers]
    return [
        dict(
            mistake=rule.mistake,
            answer=answer,
            correction=rule.correction,
            explanation=(
                _sentence_building_explanation(answer, rule.correction, rule.explanation)
                if not specific and _interaction(question) == "sentenceBuilding"
                else rule.explanation
            ),
        )
        for rule in rules
    ]


def _option_notes(evaluation, answer):
    """Explanations for ruled-out options, preserving correction-rule order."""
    given = normalize_answer(answer or "")
    notes = []
    for rule in evaluation.corrections:
        answers = {normalize_answer(item) for item in rule.answers}
        note = rule.note or rule.explanation
        if not answers or given in answers or not note or note == evaluation.correct_note:
            continue
        if note not in notes:
            notes.append(note)
    return notes


def review_details(
    task: SessionTask,
    request,
    question_results,
    correct_answers,
    server_assistance=None,
):
    """Grouped-lesson ``evaluationDetails`` with ``questionOutcomes`` added.

    Correctness comes from ``question_results``; the outcomes only describe it.
    Questions without evaluation metadata are reported as unassessed.
    """
    mission = get_mission(*task.public_content.mission_key)
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
    assistance = {item.question_id: item.supports for item in request.question_assistance or []}
    server_assistance = server_assistance or {}
    outcomes = []
    for question in task.public_content.questions:
        question_id = question.question_id
        server_supports = []
        hint = server_assistance.get(question_id) or {}
        if hint.get("hintLevel"):
            server_supports.append("hint")
        if hint.get("revealed"):
            server_supports.append("answerReveal")
        supports = list(dict.fromkeys(
            [
                *assistance.get(question_id, []),
                *server_supports,
                *_BUILT_IN_SUPPORTS.get(_interaction(question), []),
            ]
        ))
        evaluation = evaluations.get(question_id)
        common = dict(
            question_id=question_id,
            assistance=supports,
            assistance_used=any(mission.counts_as_assistance(item) for item in supports),
        )
        if evaluation is None or question_id not in question_results:
            outcomes.append(
                QuestionOutcome(
                    **common, outcome="unassessed", evidence_type=_default_evidence(question)
                )
            )
            continue
        correct = question_results[question_id]
        outcomes.append(
            QuestionOutcome(
                **common,
                outcome="correct" if correct else "incorrect",
                objective_id=evaluation.objective_id,
                target_ids=evaluation.target_ids,
                evidence_type=evaluation.evidence_type,
                correct_note=(
                    evaluation.correct_note
                    if correct and _interaction(question) == "multipleChoice" else None
                ),
                mistakes=(
                    [] if correct else _mistakes(
                        evaluation, request.answers.get(question_id), question,
                    )
                ),
                option_notes=(
                    _option_notes(evaluation, request.answers.get(question_id))
                    if correct and _interaction(question) == "multipleChoice" else []
                ),
            )
        )
    return QuestionReviewDetails(
        question_results=question_results,
        correct_answers=correct_answers,
        question_outcomes=outcomes,
    ).model_dump(mode="json")
