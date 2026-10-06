"""Provider-neutral orchestrator for model-backed I-Spy clue generation.

Builds the per-payload dynamic request model, calls a ``TextModelClient``,
then validates the response deterministically (scene grounding, clue shape,
distinct answers, and answer-leakage). Contains no provider-specific logic.
Learner-supplied content reaches the tracer only through ``record_content``,
which is gated by the capture-content setting; traced metadata carries
counts only.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from typing import Any

from app.ai.cache import (
    CacheScope,
    CacheWaitTimeout,
    FeatureVersion,
    Generated,
    ResultCache,
    generated,
    run_cached,
)
from app.ai.contracts.errors import ProviderError
from app.ai.contracts.schema import build_strict_json_schema
from app.ai.contracts.text import TextModelClient, TextModelConfig, TextModelRequest
from app.ai.features.ispy_clues.prompt import (
    ISPY_CLUE_PROMPT_VERSION,
    ISPY_CLUE_SCHEMA_VERSION,
    ISPY_CLUE_SYSTEM_PROMPT,
)
from app.ai.features.ispy_clues.schemas import (
    ISpyClueResult,
    scene_clue_response_model,
)
from app.ai.features.ispy_clues.validation import (
    ISPY_CLUE_VALIDATOR_VERSION,
    ISpyClueGenerationError,
    validate_ispy_clues,
)
from app.ai.observability import AITracer
from app.ai.routing import as_routed, route_metadata, total_tokens
from app.ai.settings import AiFeature

logger = logging.getLogger(__name__)

_ISPY_CLUES_INVALID = "ispyCluesInvalid"
_VERSION = FeatureVersion(
    AiFeature.ISPY_CLUE.value,
    ISPY_CLUE_PROMPT_VERSION,
    ISPY_CLUE_SCHEMA_VERSION,
    ISPY_CLUE_VALIDATOR_VERSION,
)
_REPAIR_INSTRUCTION = """

Your previous response was invalid. Return a complete replacement JSON object.
Every clue must help identify its assigned object without naming that object's
answer word or translation anywhere in the clue.
"""


class ISpyClueService:
    """Generates scene-grounded I-Spy clues through the text-model seam."""

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
        self, payload: dict[str, Any], *, cache_scope: CacheScope | None = None
    ) -> ISpyClueResult:
        """Generate clues for ``payload``; ``cache_scope=None`` bypasses the cache."""
        # Empty-scene guard raises ISpyClueGenerationError before any call.
        response_model = scene_clue_response_model(payload)

        def decode(data: Any) -> ISpyClueResult:
            result = ISpyClueResult.model_validate(data)
            validate_ispy_clues(payload, result)
            return result

        try:
            return run_cached(
                self._cache,
                self._client,
                version=_VERSION,
                scope=cache_scope,
                payload=payload,
                compute=lambda: self._generate(payload, response_model),
                decode=decode,
            )
        except CacheWaitTimeout as error:
            raise ISpyClueGenerationError("I-Spy clue generation failed.") from error

    def _generate(
        self, payload: dict[str, Any], response_model: Any
    ) -> Generated[ISpyClueResult]:
        content = json.dumps(payload, ensure_ascii=False)
        request = TextModelRequest(
            system_prompt=ISPY_CLUE_SYSTEM_PROMPT,
            user_content=content,
            json_schema_name="ispy_clues_v1",
            # Per-payload: key restrictions are built from this scene's keys.
            json_schema=build_strict_json_schema(response_model),
            prompt_version=ISPY_CLUE_PROMPT_VERSION,
        )

        attempts = 1 + self._config.max_retries
        invocation = self._client.start_invocation()
        latency_ms = 0.0
        with self._tracer.trace(
            "ispy-clues",
            feature=AiFeature.ISPY_CLUE.value,
            metadata={"objectCount": len(payload.get("objects", []))},
        ) as root:
            for attempt in range(1, attempts + 1):
                attempt_request = (
                    request
                    if attempt == 1
                    else replace(
                        request,
                        user_content=content + _REPAIR_INSTRUCTION,
                    )
                )
                call_start = time.perf_counter()
                try:
                    with self._tracer.generation(
                        "ispy-clue-generation",
                        feature=AiFeature.ISPY_CLUE.value,
                        provider=self._provider,
                        model=self._config.model_name,
                        prompt_version=ISPY_CLUE_PROMPT_VERSION,
                        schema_version=ISPY_CLUE_SCHEMA_VERSION,
                        model_parameters={
                            "maxOutputTokens": self._config.max_output_tokens,
                            "timeoutSeconds": self._config.timeout_seconds,
                        },
                        metadata={"attempt": attempt},
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
                        "ispy-clue-validation",
                        metadata={"attempt": attempt},
                    ) as validation:
                        try:
                            parsed = response_model.model_validate_json(
                                response.output_text
                            )
                            result = ISpyClueResult.model_validate(
                                parsed.model_dump()
                            )
                            validate_ispy_clues(payload, result)
                        except (
                            ValueError,
                            ISpyClueGenerationError,
                        ) as error:
                            validation.update(
                                validation_result="invalid",
                                error_code=_ISPY_CLUES_INVALID,
                            )
                            raise error
                        validation.update(
                            validation_result="valid",
                            metadata={"clueCount": len(result.clues)},
                        )
                    root.update(
                        retry_count=invocation.retries, validation_result="valid"
                    )
                    return generated(result, response)
                except ProviderError as error:
                    root.update(
                        retry_count=invocation.retries,
                        validation_result="invalid",
                        error_code=error.code.value,
                    )
                    raise ISpyClueGenerationError(
                        "I-Spy clue generation failed."
                    ) from error
                except (ValueError, ISpyClueGenerationError) as error:
                    if attempt < attempts and invocation.can_call():
                        logger.warning(
                            "ispy-clue output failed validation, retrying",
                            extra={"attempt": attempt},
                        )
                        continue
                    root.update(
                        retry_count=invocation.retries,
                        validation_result="invalid",
                        error_code=_ISPY_CLUES_INVALID,
                    )
                    raise ISpyClueGenerationError(
                        "I-Spy clue generation returned unusable output."
                    ) from error

            # Unreachable: every loop path either returns or raises.
            raise ISpyClueGenerationError("I-Spy clue generation failed.")
