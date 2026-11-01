"""Task-building helpers shared by every mission lesson."""

import re
from uuid import UUID, uuid5

from app.schemas.tasks import SessionTask


def definite(source):
    return f"the {re.sub(r'^(?:a|an|the)\s+', '', source, flags=re.IGNORECASE)}"


def mission_fields(mission):
    return dict(
        mission_id=mission.mission_id,
        practice_level=mission.practice_level,
        content_version=mission.content_version,
    )


def mission_version(mission):
    return f"{mission.mission_id}-{mission.practice_level}.v{mission.content_version}"


def correct_label(question):
    if question.interaction_type == "multipleChoice":
        return next(
            option.label for option in question.options
            if option.option_id == question.correct_option_id
        )
    return question.correct_text


def build_mission_task(
    session_id, mission, focus, result, evaluate, shown=lambda question: {}, content_fields=None,
):
    """One mission-tagged grammar lesson whose private key grades every question.

    ``evaluate(question, label)`` returns the question's evaluation fields and
    ``shown(question)`` any extra public question fields.
    """
    questions = result.questions
    correct, accepted = {}, {}
    evaluations = []
    for question in questions:
        label = correct_label(question)
        correct[question.question_id] = (
            question.correct_option_id
            if question.interaction_type == "multipleChoice"
            else question.correct_text
        )
        if getattr(question, "accepted_option_ids", None):
            accepted[question.question_id] = list(question.accepted_option_ids)
        evaluations.append(dict(
            question_id=question.question_id,
            objective_id=mission.objective.objective_id,
            scene_object_id=UUID(question.object_key),
            **evaluate(question, label),
        ))
    return SessionTask(
        id=uuid5(session_id, f"mission:{mission_version(mission)}:lesson"),
        session_id=session_id,
        phase="learning",
        kind="grammarLesson",
        order_index=0,
        public_content=dict(
            kind="grammarLesson",
            focus=focus,
            title=result.title,
            questions=[
                dict(
                    question_id=question.question_id,
                    prompt=question.prompt,
                    interaction_type=question.interaction_type,
                    options=[
                        dict(option_id=option.option_id, label=option.label)
                        for option in question.options
                    ],
                    token_bank=(
                        question.token_bank
                        if mission.practice_level == "A2"
                        and any(" " in chunk for chunk in question.answer_chunks)
                        else [token for token in question.token_bank if token != "."]
                    ),
                    translation=question.translation,
                    **shown(question),
                )
                for question in questions
            ],
            **mission_fields(mission),
            **(content_fields or {}),
        ),
        answer_key=dict(
            correct_option_ids=correct, accepted_option_ids=accepted,
            question_evaluations=evaluations,
        ),
        scene_object_id=UUID(questions[-1].object_key),
    )
