"""Provider-neutral learning-task feature package.

Exports are lazy (``__getattr__``) for the same reason as the translation
package: schema consumers can sit on ``app.services.scene_analysis``'s import
chain, and eagerly importing ``service``/``validation`` could close a cycle.
"""

from typing import Any

__all__ = [
    "LEARNING_TASK_PROMPT_VERSION",
    "LEARNING_TASK_SCHEMA_VERSION",
    "LEARNING_TASK_SYSTEM_PROMPT",
    "GeneratedChoice",
    "GeneratedDescriptionQuestion",
    "GeneratedLearningTask",
    "GeneratedMultipleChoiceQuestion",
    "GeneratedQuestion",
    "GeneratedSentenceBuilderQuestion",
    "KEY_FIELDS",
    "LearningTaskFocus",
    "LearningTaskGenerationError",
    "LearningTaskResult",
    "LearningTaskService",
    "REQUIRED_TASK_FOCUS_ORDER",
    "generation_response_model",
    "keys_for",
    "normalize_learning_task_option_ids",
    "normalize_learning_task_references",
    "required_task_focuses",
    "scene_generation_response_model",
    "unpack_generated_tasks",
    "validate_learning_tasks",
]

_IMPORTS = {
    "LEARNING_TASK_PROMPT_VERSION": "app.ai.features.learning_tasks.prompt",
    "LEARNING_TASK_SCHEMA_VERSION": "app.ai.features.learning_tasks.prompt",
    "LEARNING_TASK_SYSTEM_PROMPT": "app.ai.features.learning_tasks.prompt",
    "GeneratedChoice": "app.ai.features.learning_tasks.schemas",
    "GeneratedDescriptionQuestion": "app.ai.features.learning_tasks.schemas",
    "GeneratedLearningTask": "app.ai.features.learning_tasks.schemas",
    "GeneratedMultipleChoiceQuestion": "app.ai.features.learning_tasks.schemas",
    "GeneratedQuestion": "app.ai.features.learning_tasks.schemas",
    "GeneratedSentenceBuilderQuestion": "app.ai.features.learning_tasks.schemas",
    "KEY_FIELDS": "app.ai.features.learning_tasks.schemas",
    "LearningTaskFocus": "app.ai.features.learning_tasks.schemas",
    "LearningTaskResult": "app.ai.features.learning_tasks.schemas",
    "REQUIRED_TASK_FOCUS_ORDER": "app.ai.features.learning_tasks.schemas",
    "generation_response_model": "app.ai.features.learning_tasks.schemas",
    "required_task_focuses": "app.ai.features.learning_tasks.schemas",
    "scene_generation_response_model": "app.ai.features.learning_tasks.schemas",
    "unpack_generated_tasks": "app.ai.features.learning_tasks.schemas",
    "LearningTaskService": "app.ai.features.learning_tasks.service",
    "LearningTaskGenerationError": "app.ai.features.learning_tasks.validation",
    "keys_for": "app.ai.features.learning_tasks.validation",
    "normalize_learning_task_option_ids": "app.ai.features.learning_tasks.validation",
    "normalize_learning_task_references": "app.ai.features.learning_tasks.validation",
    "validate_learning_tasks": "app.ai.features.learning_tasks.validation",
}


def __getattr__(name: str) -> Any:
    module_path = _IMPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value
    return value
