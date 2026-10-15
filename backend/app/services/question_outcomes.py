"""Structured per-question results for tasks with question evaluation metadata."""

from app.missions import get_mission
from app.schemas.tasks import QuestionOutcome, QuestionReviewDetails, SessionTask


def normalize_answer(value):
    return " ".join(value.casefold().strip().split()).rstrip(".!?\u3002")


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


def _mistakes(evaluation, answer):
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
            explanation=rule.explanation,
        )
        for rule in rules
    ]


def review_details(task: SessionTask, request, question_results, correct_answers):
    """Grouped-lesson ``evaluationDetails`` with ``questionOutcomes`` added.

    Correctness comes from ``question_results``; the outcomes only describe it.
    Questions without evaluation metadata are reported as unassessed.
    """
    mission = get_mission(*task.public_content.mission_key)
    evaluations = {item.question_id: item for item in task.answer_key.question_evaluations}
    assistance = {item.question_id: item.supports for item in request.question_assistance or []}
    outcomes = []
    for question in task.public_content.questions:
        question_id = question.question_id
        supports = list(dict.fromkeys(
            [*assistance.get(question_id, []), *_BUILT_IN_SUPPORTS.get(_interaction(question), [])]
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
                evidence_type=_default_evidence(question),
                mistakes=(
                    [] if correct else _mistakes(evaluation, request.answers.get(question_id))
                ),
            )
        )
    return QuestionReviewDetails(
        question_results=question_results,
        correct_answers=correct_answers,
        question_outcomes=outcomes,
    ).model_dump(mode="json")
