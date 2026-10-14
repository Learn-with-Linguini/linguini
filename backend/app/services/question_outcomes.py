"""Structured per-question results for tasks with question evaluation metadata."""

from app.missions import get_mission
from app.schemas.tasks import QuestionOutcome, QuestionReviewDetails, SessionTask


def normalize_answer(value):
    return " ".join(value.casefold().strip().split()).rstrip(".!?\u3002")


def _default_evidence(question):
    if getattr(question, "interaction_type", "multipleChoice") == "sentenceBuilding":
        return "construction"
    return "recognition"


def _mistakes(evaluation, answer):
    given = normalize_answer(answer or "")
    return [
        dict(
            mistake=rule.mistake,
            answer=answer,
            correction=rule.correction,
            explanation=rule.explanation,
        )
        for rule in evaluation.corrections
        if not rule.answers or given in {normalize_answer(item) for item in rule.answers}
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
        supports = assistance.get(question_id, [])
        evaluation = evaluations.get(question_id)
        common = dict(
            question_id=question_id,
            assistance=supports,
            assistance_used=any(mission.counts_as_assistance(item) for item in supports),
        )
        if evaluation is None:
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
