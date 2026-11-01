"""The M05 A1 role-play lesson task and its premises."""

from app.services.lesson_tasks.common import build_mission_task

M05_FOCUS = "sayWhatYouLike"


_EVALUATIONS = {
    "choosePreference": (["choose-preference"], "recognition", ["chooses-preference"]),
    "buildMyPreference": (
        ["say-my-preference"], "construction", ["says-my-preference"]
    ),
    "buildTheirPreference": (
        ["say-their-preference"], "construction", ["says-their-preference"]
    ),
}


def subject_name(fact):
    return fact.subject_names[0] if fact.subject_names else None


def premise(fact, label):
    if fact.subject_type == "learner":
        subject = "you"
    else:
        subject = subject_name(fact)
    preference = "like" if fact.preference == "like" else "don't like"
    if subject == "you":
        return f"Let's pretend you {preference} the {label}."
    verb = "likes" if fact.preference == "like" else "doesn't like"
    return f"Let's pretend {subject} {verb} the {label}."


def m05_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """Build the public M05 grammar lesson; preference attempts never affect vocabulary."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        corrections = (
            [
                dict(
                    mistake="wrongWord",
                    answers=[option.option_id],
                    correction=label,
                    explanation=(
                        "Check whether the sentence matches the pretend like or dislike fact."
                    ),
                )
                for option in question.options if option.option_id != question.correct_option_id
            ]
            if question.interaction_type == "multipleChoice"
            else [dict(
                mistake="wordOrder",
                correction=question.correct_text,
                explanation="Use the taught like or dislike statement.",
            )]
        )
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[],
            corrections=corrections,
        )

    def shown(question):
        detail = next(
            item for item in payload["fact_details"] if item["objectKey"] == question.object_key
        )
        return dict(
            scene_object_id=question.object_key,
            object_label=detail["label"].capitalize(),
            section=question.section,
            roleplay_premise=question.roleplay_premise,
            prompt_translation=question.prompt_translation,
            keep_option_order=(
                True if question.interaction_type == "multipleChoice" else None
            ),
        )

    return build_mission_task(
        session_id,
        mission,
        M05_FOCUS,
        result,
        evaluate,
        shown,
        content_fields=dict(explanation=payload["explanation"], roleplay_facts=payload["facts"]),
    )
