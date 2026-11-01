"""The M04 A1 role-play lesson task and its premises."""

from app.services.lesson_tasks.common import build_mission_task

M04_FOCUS = "sayWhoseIsIt"


_EVALUATIONS = {
    "chooseOwner": (["choose-possessive"], "recognition", ["chooses-possessive"]),
    "buildMine": (["say-mine"], "construction", ["says-mine"]),
    "buildTheirs": (["say-theirs"], "construction", ["says-theirs"]),
}


def owner_name(fact):
    return fact.owner_names[0] if fact.owner_names else None


def premise(fact, label):
    if fact.owner_type == "learner":
        return f"Let's pretend the {label} is yours."
    return f"Let's pretend the {label} is {owner_name(fact)}'s."


def m04_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """Build the public M04 grammar lesson; its evaluations never affect vocabulary."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        corrections = (
            [
                dict(
                    mistake="wrongWord",
                    answers=[option.option_id],
                    correction=label,
                    explanation="Check whose pretend thing the sentence describes.",
                )
                for option in question.options if option.option_id != question.correct_option_id
            ]
            if question.interaction_type == "multipleChoice"
            else [dict(
                mistake="wordOrder",
                correction=question.correct_text,
                explanation="Use the taught possessive statement.",
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
        M04_FOCUS,
        result,
        evaluate,
        shown,
        content_fields=dict(explanation=payload["explanation"], roleplay_facts=payload["facts"]),
    )
