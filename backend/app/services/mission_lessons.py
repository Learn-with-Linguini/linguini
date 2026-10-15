"""Shared mission fields and the mission-tagged grammar lesson task."""

from uuid import UUID, uuid5

from app.schemas.tasks import SessionTask


def mission_fields(mission):
    return dict(
        mission_id=mission.mission_id,
        practice_level=mission.practice_level,
        content_version=mission.content_version,
    )


def mission_version(mission):
    return f"{mission.mission_id}-{mission.practice_level}.v{mission.content_version}"


def with_mission(task, mission):
    """``task`` snapshotted to ``mission``'s ID, level and content version."""
    data = task.model_dump(by_alias=False)
    data["public_content"] = {**data["public_content"], **mission_fields(mission)}
    return SessionTask.model_validate(data)


def noun_gender(term, word):
    if term is not None and term.gender:
        return term.gender
    return getattr(word.gender, "value", word.gender)


def correct_label(question):
    if question.interaction_type == "multipleChoice":
        return next(
            option.label for option in question.options
            if option.option_id == question.correct_option_id
        )
    return question.correct_text


def build_mission_task(session_id, mission, focus, result, evaluate):
    """One mission-tagged grammar lesson whose private key grades every question.

    ``evaluate(question, label)`` returns the question's evaluation fields.
    """
    questions = result.questions
    correct = {}
    evaluations = []
    for question in questions:
        label = correct_label(question)
        correct[question.question_id] = (
            question.correct_option_id
            if question.interaction_type == "multipleChoice"
            else question.correct_text
        )
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
            explanation=result.explanation,
            questions=[
                dict(
                    question_id=question.question_id,
                    prompt=question.prompt,
                    interaction_type=question.interaction_type,
                    options=[
                        dict(option_id=option.option_id, label=option.label)
                        for option in question.options
                    ],
                    token_bank=question.token_bank,
                    translation=question.translation,
                )
                for question in questions
            ],
            **mission_fields(mission),
        ),
        answer_key=dict(correct_option_ids=correct, question_evaluations=evaluations),
        scene_object_id=UUID(questions[-1].object_key),
    )
