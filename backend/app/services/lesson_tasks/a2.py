"""A2 lesson tasks for M01-M04."""

from uuid import UUID

from app.services.lesson_tasks.common import build_mission_task

_META = {
    "M01": {
        "chooseSceneMarker": (
            ["identify-scene-object"],
            "objectSelection",
            ["scene-object-matches-fact"],
        ),
        "buildSceneFact": (
            ["describe-scene-facts"],
            "construction",
            ["scene-sentence-matches-facts"],
        ),
        "chooseSceneDescription": (
            ["describe-scene-facts"],
            "recognition",
            ["scene-sentence-matches-facts"],
        ),
        "buildSceneDescription": (
            ["connect-scene-facts"],
            "construction",
            ["scene-facts-connected"],
        ),
        "followUpSceneFact": (["follow-up-scene-fact"], "recognition", ["scene-follow-up-matches"]),
    },
    "M02": {
        "readAttributeClue": (["understand-target-clues"], "recognition", ["target-clue-matches"]),
        "buildLocationClue": (["understand-target-clues"], "construction", ["target-clue-matches"]),
        "chooseUniqueTarget": (
            ["find-target-object"],
            "objectSelection",
            ["both-clues-find-target"],
        ),
        "clarifyDistractor": (["clarify-target"], "recognition", ["clarification-corrects-target"]),
        "buildTargetSentence": (
            ["name-located-target"],
            "construction",
            ["target-is-named-and-located"],
        ),
    },
    "M03": {
        "countGroup": (["understand-counts"], "recognition", ["count-matches-photo"]),
        "buildQuantity": (["describe-counts"], "construction", ["quantity-sentence-matches"]),
        "compareGroups": (["compare-counts"], "recognition", ["comparison-direction-correct"]),
        "correctRoleplayCount": (
            ["correct-count-mistake"],
            "recognition",
            ["count-correction-correct"],
        ),
        "buildComparison": (["compare-counts"], "construction", ["comparison-direction-correct"]),
    },
    "M04": {
        "chooseAssignedObject": (
            ["identify-owned-object"],
            "objectSelection",
            ["assigned-object-matches"],
        ),
        "choosePossessive": (["use-possessive"], "recognition", ["possessive-agrees"]),
        "clarifyOwnership": (["clarify-ownership"], "recognition", ["ownership-clarified"]),
        "buildBelonging": (["describe-belonging"], "construction", ["belonging-described"]),
        "buildOwnershipDescription": (
            ["describe-belonging"],
            "construction",
            ["belonging-described"],
        ),
    },
}


def _task(session_id, mission, payload, result, vocabulary_ids):
    from app.schemas.tasks import SessionTask

    mission_id = mission.mission_id
    question_meta = _META[mission_id]

    def evaluate(question, _label):
        target_ids, evidence_type, criteria = question_meta[question.purpose]
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=(
                [vocabulary_ids[question.object_key]]
                if question.object_key in vocabulary_ids
                and question.purpose not in {"correctRoleplayCount", "clarifyOwnership"}
                else []
            ),
        )

    def shown(question):
        fields = {
            "section": question.section,
            "keep_option_order": True if question.interaction_type == "multipleChoice" else None,
        }
        if question.roleplay_premise:
            fields["roleplay_premise"] = question.roleplay_premise
        if question.planning_facts:
            fields["planning_facts"] = question.planning_facts
        if question.marker_object_ids:
            fields["marker_object_ids"] = {
                key: UUID(value) for key, value in question.marker_object_ids.items()
            }
        if question.group_object_ids:
            fields["group_object_ids"] = [UUID(value) for value in question.group_object_ids]
        return fields

    task = build_mission_task(
        session_id, mission, f"sceneMission{mission_id}A2", result, evaluate, shown
    )
    data = task.model_dump(by_alias=False)
    data["public_content"]["check_each_question"] = True
    data["answer_key"]["mission_state"] = {
        "approvedFacts": payload["approvedFacts"],
        "selection": payload["selection"],
        "seed": payload["seed"],
    }
    return SessionTask.model_validate(data)


def m01_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m02_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m03_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m04_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)
