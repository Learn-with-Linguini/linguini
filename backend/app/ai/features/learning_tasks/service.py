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
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, ValidationError

from app.ai.cache import (
    CacheScope,
    CacheWaitTimeout,
    FeatureVersion,
    Generated,
    ResultCache,
    TemplateSet,
    generated,
    run_cached,
)
from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.schema import build_strict_json_schema
from app.ai.contracts.text import TextModelClient, TextModelConfig, TextModelRequest
from app.ai.features.learning_tasks.prompt import (
    LEARNING_TASK_MEMORY_PROMPT_VERSION,
    LEARNING_TASK_MEMORY_SYSTEM_PROMPT,
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
    LEARNING_TASK_VALIDATOR_VERSION,
    LearningTaskGenerationError,
    normalize_learning_task_option_ids,
    normalize_learning_task_references,
    restore_missing_object_keys,
    validate_learning_tasks,
)
from app.ai.observability import AITracer
from app.ai.routing import as_routed, route_metadata, total_tokens
from app.ai.settings import AiFeature
from app.schemas.base import ApiModel

logger = logging.getLogger(__name__)

_LEARNING_TASKS_INVALID = "learningTasksInvalid"
_VERSION = FeatureVersion(
    AiFeature.LEARNING_TASK.value,
    LEARNING_TASK_PROMPT_VERSION,
    LEARNING_TASK_SCHEMA_VERSION,
    LEARNING_TASK_VALIDATOR_VERSION,
)
_MEMORY_VERSION = replace(_VERSION, prompt_version=LEARNING_TASK_MEMORY_PROMPT_VERSION)
_REPAIR_INSTRUCTION = """

Your previous response was incomplete. Return a complete replacement JSON object.
Every task must include a non-empty title and 2 to 4 questions. Every question
must include at least one object key. Sentence-building questions must include a
non-empty English translation of their completed correct sentence.
"""

_Count = Annotated[int, Field(ge=0)]
_Term = Annotated[str, Field(min_length=1, max_length=64)]
_MAX_HISTORY_BYTES = 6 * 1024


class _HistoryModel(ApiModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _HistoryProfile(_HistoryModel):
    source_language: Annotated[str, Field(min_length=2, max_length=35)]
    target_language: Annotated[str, Field(min_length=2, max_length=35)]
    proficiency_level: Literal["A1", "A2", "B1", "B2", "C1", "C2"]


class _HistoryTotals(_HistoryModel):
    sessions_completed: _Count
    graded_attempts: _Count
    reading_tasks_completed: _Count
    journals_completed: _Count


class _HistoryGraded(_HistoryModel):
    correct_count: _Count
    incorrect_count: _Count
    last_outcome: Literal["correct", "incorrect"] | None


class _HistoryWord(_HistoryGraded):
    term: _Term
    source: _Term
    seen_count: _Count
    journal_mentions: _Count
    assisted_journal_mentions: _Count
    journal_selections: _Count
    relevant: bool


class _HistoryGrammar(_HistoryModel):
    gender_number_agreement: _HistoryGraded
    plural_noun_form: _HistoryGraded
    scene_description: _HistoryGraded
    chained_description: _HistoryGraded


class _HistoryCorrections(_HistoryModel):
    grammar: _Count
    spelling: _Count
    syntax: _Count
    vocabulary: _Count
    clarity: _Count


class _HistoryJournal(_HistoryModel):
    accepted_corrections: _HistoryCorrections


class _LearnerHistory(_HistoryModel):
    version: Literal[1]
    profile: _HistoryProfile
    totals: _HistoryTotals
    words: Annotated[list[_HistoryWord], Field(max_length=16)]
    grammar: _HistoryGrammar
    journal: _HistoryJournal


def _history_payload(payload):
    """Keep prose/identifiers and unbounded history out of the model boundary."""
    history = payload.get("learnerHistory")
    if history is None:
        return {key: value for key, value in payload.items() if key != "learnerHistory"}, False
    if not isinstance(history, dict) or type(history.get("version")) is not int:
        raise LearningTaskGenerationError("Learner history must be a bounded versioned summary.")
    try:
        encoded = json.dumps(history, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise LearningTaskGenerationError(
            "Learner history must be a bounded versioned summary."
        ) from None
    if len(encoded) > _MAX_HISTORY_BYTES:
        raise LearningTaskGenerationError("Learner history exceeds the summary size limit.")
    try:
        validated = _LearnerHistory.model_validate(history)
    except ValidationError:
        raise LearningTaskGenerationError(
            "Learner history must be a bounded versioned summary."
        ) from None
    if (
        validated.profile.target_language.casefold()
        != str(payload.get("targetLanguage", "")).casefold()
    ):
        raise LearningTaskGenerationError(
            "Learner history must match the current learning language."
        )
    expected_profile = {
        "sourceLanguage": validated.profile.source_language,
        "proficiencyLevel": validated.profile.proficiency_level,
    }
    if any(
        key in payload and str(payload[key]).casefold() != value.casefold()
        for key, value in expected_profile.items()
    ):
        raise LearningTaskGenerationError(
            "Learner history must match the current learning profile."
        )
    return {**payload, "learnerHistory": validated.model_dump(mode="json", by_alias=True)}, True


class LearningTaskService:
    """Generates grammar tasks through the text-model seam."""

    def __init__(
        self,
        client: TextModelClient,
        config: TextModelConfig,
        *,
        tracer: AITracer,
        provider: str,
        cache: ResultCache | None = None,
    ) -> None:
        self._client = as_routed(client, config, kind="text")
        self._cache = cache
        self._config = config
        self._tracer = tracer
        self._provider = provider

    def generate(
        self, payload: dict[str, Any], *, cache_scope: CacheScope | None = None,
        templates: TemplateSet | None = None,
    ) -> LearningTaskResult:
        """Generate tasks for ``payload``; ``cache_scope=None`` bypasses the cache."""
        payload, personal = _history_payload(payload)
        version = _MEMORY_VERSION if personal else _VERSION
        system_prompt = (
            LEARNING_TASK_MEMORY_SYSTEM_PROMPT if personal else LEARNING_TASK_SYSTEM_PROMPT
        )
        if personal:
            # A curated scene's templates must never store or replace a personal lesson.
            templates = None
            if cache_scope == CacheScope.public():
                cache_scope = None
        focuses = required_task_focuses(payload)
        payload = {**payload, "requiredTaskFocuses": list(focuses)}
        # Empty-scene guard raises LearningTaskGenerationError before any call.
        response_model = scene_generation_response_model(payload)

        def decode(data: Any) -> LearningTaskResult:
            result = LearningTaskResult.model_validate(data)
            validate_learning_tasks(payload, result)
            return result

        try:
            return run_cached(
                self._cache,
                self._client,
                version=version,
                scope=cache_scope,
                payload=payload,
                compute=lambda: self._generate(
                    payload,
                    focuses,
                    response_model,
                    prompt_version=version.prompt_version,
                    system_prompt=system_prompt,
                ),
                decode=decode,
                templates=templates,
            )
        except CacheWaitTimeout as error:
            raise LearningTaskGenerationError("Learning task generation failed.") from error

    def _generate(
        self,
        payload: dict[str, Any],
        focuses: tuple[str, ...],
        response_model: Any,
        *,
        prompt_version: str = LEARNING_TASK_PROMPT_VERSION,
        system_prompt: str = LEARNING_TASK_SYSTEM_PROMPT,
    ) -> Generated[LearningTaskResult]:
        content = json.dumps(payload, ensure_ascii=False)
        request = TextModelRequest(
            system_prompt=system_prompt,
            user_content=content,
            json_schema_name="learning_tasks_v2",
            # Per-payload: key enums are built from this scene's keys.
            json_schema=build_strict_json_schema(response_model),
            prompt_version=prompt_version,
        )

        attempts = 1 + self._config.max_retries
        invocation = self._client.start_invocation()
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
                        prompt_version=prompt_version,
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
                            response = self._client.generate(attempt_request, invocation=invocation)
                        except ProviderError as error:
                            generation.update(
                                error_code=error.code.value,
                                retry_count=invocation.retries,
                            )
                            raise
                        latency_ms += (time.perf_counter() - call_start) * 1000
                        generation.update(
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            total_tokens=total_tokens(response),
                            metadata=route_metadata(response),
                            latency_ms=latency_ms,
                            retry_count=invocation.retries,
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
                        retry_count=invocation.retries, validation_result="valid"
                    )
                    return generated(result, response)
                except ProviderError as error:
                    if (error.code is ProviderErrorCode.PROVIDER_RESPONSE_INVALID
                            and attempt < attempts and invocation.can_call()):
                        continue
                    root.update(
                        retry_count=invocation.retries,
                        validation_result="invalid",
                        error_code=error.code.value,
                    )
                    raise LearningTaskGenerationError(
                        "Learning task generation failed."
                    ) from error
                except (ValueError, LearningTaskGenerationError) as error:
                    if attempt < attempts and invocation.can_call():
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
                        retry_count=invocation.retries,
                        validation_result="invalid",
                        error_code=_LEARNING_TASKS_INVALID,
                    )
                    raise LearningTaskGenerationError(
                        "Learning task generation returned unusable output."
                    ) from error

            # Unreachable: every loop path either returns or raises.
            raise LearningTaskGenerationError("Learning task generation failed.")
