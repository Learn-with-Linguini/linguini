"""Provider-neutral, deterministic validation for generated learning tasks.

No SDK imports: the same rules run regardless of which adapter produced the
response. ``LearningTaskGenerationError`` stays a ``SceneAnalysisError`` so
the workflow fallback and learning-error handling are unchanged.
"""

from __future__ import annotations

from typing import Any

from app.ai.features.learning_tasks.schemas import (
    KEY_FIELDS,
    LearningTaskResult,
    required_task_focuses,
)
from app.services.scene_analysis import SceneAnalysisError


class LearningTaskGenerationError(SceneAnalysisError):
    """The scene vocabulary could not be turned into usable learning tasks."""


def restore_missing_object_keys(payload: dict[str, Any], response: Any) -> Any:
    """Recover omitted object references from explicit scene links, before parsing.

    Never guess from sentence text or replace an invalid, nonempty key list.
    The dynamic response model still validates every recovered reference.
    """
    if not isinstance(response, dict):
        return response
    objects = {row["key"] for row in payload.get("objects", [])}
    links = {
        "attributeKeys": {
            row["key"]: [row.get("objectKey")]
            for row in payload.get("attributes", [])
        },
        "relationshipKeys": {
            row["key"]: [row.get("subjectObjectKey"), row.get("referenceObjectKey")]
            for row in payload.get("relationships", [])
        },
    }
    for focus in required_task_focuses(payload):
        task = response.get(focus)
        if not isinstance(task, dict) or not isinstance(task.get("questions"), list):
            continue
        for question in task["questions"]:
            if not isinstance(question, dict) or question.get("objectKeys") != []:
                continue
            recovered = []
            for field, references in links.items():
                keys = question.get(field, [])
                if not isinstance(keys, list):
                    continue
                for key in keys:
                    if isinstance(key, str):
                        recovered.extend(
                            value for value in references.get(key, []) if value in objects
                        )
            if recovered:
                question["objectKeys"] = list(dict.fromkeys(recovered))
    return response


def normalize_learning_task_references(
    payload: dict[str, Any], result: LearningTaskResult
) -> LearningTaskResult:
    """Repair unambiguous relation labels without guessing a spatial relationship."""
    rows = payload.get("relationships", [])
    relationship_keys = {row["key"] for row in rows}
    def label(value):
        return " ".join(value.casefold().replace("_", " ").split())

    for task in result.tasks:
        for question in task.questions:
            resolved = []
            for key in question.relationship_keys:
                if key in relationship_keys:
                    resolved.append(key)
                    continue
                matches = [row for row in rows if label(key) in {
                    label(row.get("source", "")), label(row.get("translation", ""))
                }]
                if len(matches) > 1:
                    objects = set(question.object_keys)
                    matches = [row for row in matches if
                        row.get("subjectObjectKey") in objects
                        and row.get("referenceObjectKey") in objects]
                if len(matches) == 1:
                    resolved.append(matches[0]["key"])
                else:
                    # Preserve invalid references so validation can report them.
                    resolved.append(key)
            question.relationship_keys = list(dict.fromkeys(resolved))
    return result


def normalize_learning_task_option_ids(result: LearningTaskResult) -> LearningTaskResult:
    """Repair opaque model-generated IDs without changing learner-facing choices."""
    for task in result.tasks:
        for question in task.questions:
            option_ids = [option.option_id for option in question.options]
            if len(option_ids) == len(set(option_ids)):
                continue
            correct_index = next(
                (
                    index
                    for index, option_id in enumerate(option_ids)
                    if option_id == question.correct_option_id
                ),
                None,
            )
            if correct_index is None:
                # Preserve this malformed response for the existing clear error.
                continue
            for index, option in enumerate(question.options, start=1):
                option.option_id = f"{question.question_id}-option-{index}"
            question.correct_option_id = question.options[correct_index].option_id
    return result


def validate_learning_tasks(payload: dict[str, Any], result: LearningTaskResult) -> None:
    expected_focuses = required_task_focuses(payload)
    actual_focuses = tuple(task.focus for task in result.tasks)
    if actual_focuses != expected_focuses:
        raise LearningTaskGenerationError(
            "Learning tasks must be "
            f"{', '.join(expected_focuses)}; received {', '.join(actual_focuses) or 'none'}."
        )
    supplied = {
        field: {row["key"] for row in payload.get(field, [])} for field in KEY_FIELDS
    }
    for task in result.tasks:
        if len({question.question_id for question in task.questions}) != len(task.questions):
            raise LearningTaskGenerationError("Question ids must be unique within a task.")
        for question in task.questions:
            option_ids = [option.option_id for option in question.options]
            if len(set(option_ids)) != len(option_ids):
                raise LearningTaskGenerationError("Option ids must be unique within a question.")
            if question.interaction_type == "multipleChoice":
                if len(question.options) != 4 or question.correct_option_id not in option_ids:
                    raise LearningTaskGenerationError(
                        "Every multiple-choice question needs four options and one correct answer."
                    )
            elif task.focus != "chainedDescription":
                raise LearningTaskGenerationError(
                    "Only chained-description tasks may use sentence building."
                )
            referenced = 0
            for field, attribute in KEY_FIELDS.items():
                keys = set(getattr(question, attribute))
                if not keys <= supplied[field]:
                    raise LearningTaskGenerationError(
                        f"Learning tasks referenced {field} outside the supplied scene."
                    )
                referenced += len(keys)
            if not referenced:
                raise LearningTaskGenerationError(
                    "Every question must reuse vocabulary supplied by the scene."
                )
            if task.focus in {"sceneDescription", "chainedDescription"} and not (
                question.translation or ""
            ).strip():
                raise LearningTaskGenerationError(
                    "Description questions need an English translation."
                )
            if task.focus == "sceneDescription" and len(
                keys_for(question, "relationship_keys")
            ) < 1:
                raise LearningTaskGenerationError(
                    f"Question {question.question_id} has no resolvable scene relationship."
                )
            if task.focus == "chainedDescription" and (
                question.interaction_type != "sentenceBuilding"
                or len(keys_for(question, "relationship_keys"))
                < min(1, len(supplied["relationships"]))
            ):
                raise LearningTaskGenerationError(
                    "Sentence building must use the relationships available in the scene."
                )


def keys_for(question, attribute: str) -> set[str]:
    return set(getattr(question, attribute))
