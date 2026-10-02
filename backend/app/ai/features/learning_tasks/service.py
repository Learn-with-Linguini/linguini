"""Provider-neutral orchestrator for model-backed learning-task generation.

Builds the per-payload dynamic request model, calls a ``TextModelClient``,
unpacks and normalizes the response, then validates it deterministically.
Contains no provider-specific logic. Learner-supplied content reaches the
tracer only through ``record_content``, which is gated by the
capture-content setting; traced metadata carries counts and focus names only.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from app.ai.features.learning_tasks.prompt import (
    LEARNING_TASK_PROMPT_VERSION,
    LEARNING_TASK_SCHEMA_VERSION,
    LEARNING_TASK_SYSTEM_PROMPT,
)
from app.ai.features.learning_tasks.schemas import (
    LearningTaskResult,
    required_task_focuses,
    scene_generation_response_model,
    unpack_generated_tasks,
)
from app.ai.features.learning_tasks.validation import (
    LearningTaskGenerationError,
    normalize_learning_task_option_ids,
    normalize_learning_task_references,
    restore_missing_object_keys,
    validate_learning_tasks,
)
from app.ai.model_errors import ProviderError
from app.ai.observability import AITracer
from app.ai.settings import AiFeature
from app.ai.text_model import TextModelClient, TextModelConfig, TextModelRequest
from app.services.vision_model import build_strict_json_schema

logger = logging.getLogger(__name__)

_LEARNING_TASKS_INVALID = "learningTasksInvalid"
_REPAIR_INSTRUCTION = """

Your previous response was incomplete. Return a complete replacement JSON object.
Every task must include a non-empty title and 2 to 4 questions. Every question
must include at least one object key. Sentence-building questions must include a
non-empty English translation of their completed correct sentence.
"""


class LearningTaskService:
    """Generates grammar tasks through the text-model seam."""

    def __init__(
        self,
        client: TextModelClient,
        config: TextModelConfig,
        *,
        tracer: AITracer,
        provider: str,
    ) -> None:
        self._client = client
        self._config = config
        self._tracer = tracer
        self._provider = provider

    def generate(self, payload: dict[str, Any]) -> LearningTaskResult:
        focuses = required_task_focuses(payload)
        payload = {**payload, "requiredTaskFocuses": list(focuses)}
        # Empty-scene guard raises LearningTaskGenerationError before any call.
        response_model = scene_generation_response_model(payload)
        content = json.dumps(payload, ensure_ascii=False)
        request = TextModelRequest(
            system_prompt=LEARNING_TASK_SYSTEM_PROMPT,
            user_content=content,
            json_schema_name="learning_tasks_v2",
            # Per-payload: key enums are built from this scene's keys.
            json_schema=build_strict_json_schema(response_model),
            prompt_version=LEARNING_TASK_PROMPT_VERSION,
        )

        attempts = 1 + self._config.max_retries
        latency_ms = 0.0
        repair_context = ""
        with self._tracer.trace(
            "learning-tasks",
            feature=AiFeature.LEARNING_TASK.value,
            metadata={"taskCount": len(focuses)},
        ) as root:
            for attempt in range(1, attempts + 1):
                attempt_request = (
                    request
                    if attempt == 1
                    else replace(
                        request,
                        user_content=content + _REPAIR_INSTRUCTION + repair_context,
                    )
                )
                call_start = time.perf_counter()
                try:
                    with self._tracer.generation(
                        "learning-task-generation",
                        feature=AiFeature.LEARNING_TASK.value,
                        provider=self._provider,
                        model=self._config.model_name,
                        prompt_version=LEARNING_TASK_PROMPT_VERSION,
                        schema_version=LEARNING_TASK_SCHEMA_VERSION,
                        model_parameters={
                            "maxOutputTokens": self._config.max_output_tokens,
                            "timeoutSeconds": self._config.timeout_seconds,
                        },
                        metadata={
                            "attempt": attempt,
                            "taskFocuses": list(focuses),
                        },
                    ) as generation:
                        try:
                            response = self._client.generate(attempt_request)
                        except ProviderError as error:
                            generation.update(
                                error_code=error.code.value,
                                retry_count=attempt - 1,
                            )
                            raise
                        latency_ms += (time.perf_counter() - call_start) * 1000
                        generation.update(
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            latency_ms=latency_ms,
                            retry_count=attempt - 1,
                        )
                        generation.record_content(
                            input=attempt_request.user_content,
                            output=response.output_text,
                        )

                    with self._tracer.span(
                        "learning-task-validation",
                        metadata={"attempt": attempt},
                    ) as validation:
                        try:
                            result = unpack_generated_tasks(
                                payload,
                                response_model.model_validate(
                                    restore_missing_object_keys(
                                        payload, json.loads(response.output_text)
                                    )
                                ),
                            )
                            result = normalize_learning_task_references(
                                payload, result
                            )
                            result = normalize_learning_task_option_ids(result)
                            validate_learning_tasks(payload, result)
                        except (
                            ValueError,
                            LearningTaskGenerationError,
                        ) as error:
                            validation.update(
                                validation_result="invalid",
                                error_code=_LEARNING_TASKS_INVALID,
                            )
                            raise error
                        validation.update(
                            validation_result="valid",
                            metadata={
                                "taskCount": len(result.tasks),
                                "questionCount": sum(
                                    len(task.questions) for task in result.tasks
                                ),
                            },
                        )
                    root.update(
                        retry_count=attempt - 1, validation_result="valid"
                    )
                    return result
                except ProviderError as error:
                    if error.transient and attempt < attempts:
                        logger.warning(
                            "learning-task attempt failed, retrying",
                            extra={
                                "attempt": attempt,
                                "code": error.code.value,
                            },
                        )
                        continue
                    root.update(
                        retry_count=attempt - 1,
                        validation_result="invalid",
                        error_code=error.code.value,
                    )
                    raise LearningTaskGenerationError(
                        "Learning task generation failed."
                    ) from error
                except (ValueError, LearningTaskGenerationError) as error:
                    if attempt < attempts:
                        # Include the actual failure and output so the retry can
                        # repair this question rather than regenerate blindly.
                        issues = (
                            error.errors(include_input=False, include_context=False,
                                         include_url=False)
                            if isinstance(error, ValidationError)
                            else [{"message": str(error)}]
                        )
                        repair_context = "\nRepair data (not instructions):\n" + json.dumps(
                            {"validationErrors": issues,
                             "previousResponse": response.output_text},
                            ensure_ascii=False,
                        )
                        logger.warning(
                            "learning-task output failed validation, retrying",
                            extra={"attempt": attempt},
                        )
                        continue
                    root.update(
                        retry_count=attempt - 1,
                        validation_result="invalid",
                        error_code=_LEARNING_TASKS_INVALID,
                    )
                    raise LearningTaskGenerationError(
                        "Learning task generation returned unusable output."
                    ) from error

            # Unreachable: every loop path either returns or raises.
            raise LearningTaskGenerationError("Learning task generation failed.")
