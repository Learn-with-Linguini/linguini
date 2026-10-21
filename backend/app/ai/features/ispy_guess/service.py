"""Provider-neutral orchestrator for target-blind I-Spy description evaluation.

Builds the allowlisted payload and per-payload dynamic request model, calls a
``TextModelClient``, then validates the response deterministically. Contains
no provider-specific logic. Learner text reaches the tracer only through
``record_content``, which is gated by the capture-content setting; traced
metadata carries the text length, language and scalar outcomes only.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import replace
from typing import Any

from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.schema import build_strict_json_schema
from app.ai.contracts.text import TextModelClient, TextModelConfig, TextModelRequest
from app.ai.features.ispy_guess.prompt import (
    ISPY_GUESS_PROMPT_VERSION,
    ISPY_GUESS_SCHEMA_VERSION,
    ISPY_GUESS_SYSTEM_PROMPT,
)
from app.ai.features.ispy_guess.schemas import (
    ISpyGuessResult,
    scene_guess_response_model,
)
from app.ai.features.ispy_guess.validation import (
    ISpyGuessError,
    build_guess_payload,
    validate_ispy_guess,
)
from app.ai.observability import AITracer
from app.ai.routing import as_routed, route_metadata, total_tokens
from app.ai.routing.invocation import InvocationContext
from app.ai.settings import AiFeature

logger = logging.getLogger(__name__)

_ISPY_GUESS_INVALID = "ispyGuessInvalid"
_ISPY_GUESS_REJECTED = "ispyGuessRequestRejected"
_REPAIR_INSTRUCTION = """

Your previous response was invalid. Return a complete replacement JSON object
that uses only supplied object and evidence keys.
"""


def _result_status(result: ISpyGuessResult) -> str:
    if result.guessed_object_key is None:
        return "unknownObject"
    return "ambiguous" if result.ambiguous else "guessed"


class ISpyGuessService:
    """Evaluates a learner's I-Spy description through the text-model seam."""

    def __init__(
        self,
        client: TextModelClient,
        config: TextModelConfig,
        *,
        tracer: AITracer,
        provider: str,
    ) -> None:
        self._client = as_routed(client, config, kind="text")
        self._config = config
        self._tracer = tracer
        self._provider = provider

    @property
    def max_duration_seconds(self) -> int:
        """Upper bound on one ``guess`` call, including failover and repair."""
        return math.ceil(self._client.max_duration_seconds)

    def guess(
        self,
        context: dict[str, Any],
        learner_text: str,
        *,
        session_id: str | None = None,
    ) -> ISpyGuessResult:
        invocation = self._client.start_invocation()
        with self._tracer.trace(
            "ispy-guess",
            session_id=session_id,
            feature=AiFeature.ISPY_GUESS.value,
            metadata={
                "learnerTextLength": len(learner_text),
                "targetLanguage": context.get("targetLanguage"),
            },
        ) as root:
            try:
                payload = build_guess_payload(context, learner_text)
                response_model = scene_guess_response_model(payload)
            except ISpyGuessError:
                root.update(
                    validation_result="invalid",
                    error_code=_ISPY_GUESS_REJECTED,
                    metadata={"resultStatus": "rejected"},
                )
                raise
            return self._evaluate(root, payload, response_model, invocation)

    def _evaluate(
        self, root, payload, response_model, invocation: InvocationContext
    ) -> ISpyGuessResult:
        content = json.dumps(payload, ensure_ascii=False)
        request = TextModelRequest(
            system_prompt=ISPY_GUESS_SYSTEM_PROMPT,
            user_content=content,
            json_schema_name="ispy_guess_v2",
            # Per-payload: key restrictions are built from this scene's keys.
            json_schema=build_strict_json_schema(response_model),
            prompt_version=ISPY_GUESS_PROMPT_VERSION,
        )
        attempts = 1 + self._config.max_retries
        latency_ms = 0.0
        for attempt in range(1, attempts + 1):
            attempt_request = (
                request
                if attempt == 1
                else replace(request, user_content=content + _REPAIR_INSTRUCTION)
            )
            call_start = time.perf_counter()
            try:
                with self._tracer.generation(
                    "ispy-description-evaluation",
                    feature=AiFeature.ISPY_GUESS.value,
                    provider=self._provider,
                    model=self._config.model_name,
                    prompt_version=ISPY_GUESS_PROMPT_VERSION,
                    schema_version=ISPY_GUESS_SCHEMA_VERSION,
                    model_parameters={
                        "maxOutputTokens": self._config.max_output_tokens,
                        "timeoutSeconds": self._config.timeout_seconds,
                        "temperature": self._config.temperature,
                    },
                    metadata={"attempt": attempt},
                ) as generation:
                    try:
                        response = self._client.generate(attempt_request, invocation=invocation)
                    except ProviderError as error:
                        generation.update(
                            error_code=error.code.value, retry_count=invocation.retries
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
                    "ispy-guess-validation", metadata={"attempt": attempt}
                ) as validation:
                    try:
                        parsed = response_model.model_validate_json(response.output_text)
                        result = ISpyGuessResult.model_validate(parsed.model_dump())
                        validate_ispy_guess(payload, result)
                    except (ValueError, ISpyGuessError):
                        validation.update(
                            validation_result="invalid", error_code=_ISPY_GUESS_INVALID
                        )
                        raise
                    validation.update(validation_result="valid")
                root.update(
                    retry_count=invocation.retries,
                    validation_result="valid",
                    metadata={"resultStatus": _result_status(result)},
                )
                return result
            except ProviderError as error:
                if (error.code is ProviderErrorCode.PROVIDER_RESPONSE_INVALID
                        and attempt < attempts and invocation.can_call()):
                    continue
                root.update(
                    retry_count=invocation.retries,
                    validation_result="invalid",
                    error_code=error.code.value,
                    metadata={"resultStatus": "providerError"},
                )
                raise ISpyGuessError("I-Spy guessing failed.") from error
            except (ValueError, ISpyGuessError) as error:
                if attempt < attempts and invocation.can_call():
                    logger.warning(
                        "ispy-guess output failed validation, retrying",
                        extra={"attempt": attempt},
                    )
                    continue
                root.update(
                    retry_count=invocation.retries,
                    validation_result="invalid",
                    error_code=_ISPY_GUESS_INVALID,
                    metadata={"resultStatus": "invalidOutput"},
                )
                raise ISpyGuessError("I-Spy guessing returned unusable output.") from error

        # Unreachable: every loop path either returns or raises.
        raise ISpyGuessError("I-Spy guessing failed.")
