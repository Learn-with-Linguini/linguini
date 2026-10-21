"""Re-export shim: the learning-task contracts now live in the feature package.

``app.ai.features.learning_tasks.schemas`` owns the generated-task models and
the dynamic response-model machinery; this module stays so existing imports
(``LearningTaskResult`` and friends) keep working unchanged.
"""

from app.ai.features.learning_tasks.schemas import (
    REQUIRED_TASK_FOCUS_ORDER,
    GeneratedChoice,
    GeneratedDescriptionQuestion,
    GeneratedLearningTask,
    GeneratedMultipleChoiceQuestion,
    GeneratedQuestion,
    GeneratedSentenceBuilderQuestion,
    LearningTaskFocus,
    LearningTaskResult,
)

__all__ = [
    "GeneratedChoice",
    "GeneratedDescriptionQuestion",
    "GeneratedLearningTask",
    "GeneratedMultipleChoiceQuestion",
    "GeneratedQuestion",
    "GeneratedSentenceBuilderQuestion",
    "LearningTaskFocus",
    "LearningTaskResult",
    "REQUIRED_TASK_FOCUS_ORDER",
]
