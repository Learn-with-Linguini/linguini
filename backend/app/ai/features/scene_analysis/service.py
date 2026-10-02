"""Provider-neutral orchestrator for model-backed uploaded scene analysis.

Builds the shared versioned request, calls a ``VisionModelClient``, validates
the returned text locally, and maps it onto domain objects. Performs no
database writes and contains no provider-specific logic.
"""

from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from app.ai.features.moderation import ImageModerationError, ImageModerator
from app.ai.features.object_grounding import ObjectGrounder, ObjectGroundingError
from app.ai.features.object_grounding.mapping import apply_object_grounding
from app.ai.features.scene_analysis.mapping import model_result_to_domain
from app.ai.features.scene_analysis.prompt import (
    SCENE_ANALYSIS_PROMPT_VERSION,
    SCENE_ANALYSIS_SCHEMA_VERSION,
    SCENE_ANALYSIS_SYSTEM_PROMPT,
    SCENE_ANALYSIS_USER_INSTRUCTION,
)
from app.ai.features.scene_analysis.schemas import SceneAnalysisModelResult
from app.ai.features.scene_analysis.validation import (
    SceneAnalysisValidationError,
    parse_scene_analysis,
)
from app.ai.observability import AITracer
from app.ai.settings import AiFeature
from app.schemas.media import MediaAsset
from app.schemas.sessions import Session
from app.services.image_storage import ImageStorage
from app.services.scene_analysis import (
    SceneAnalysisError,
    SceneAnalysisResult,
)
from app.services.vision_model import (
    VisionImage,
    VisionModelClient,
    VisionModelConfig,
    VisionModelError,
    VisionModelErrorCode,
    VisionModelRequest,
    build_strict_json_schema,
)

logger = logging.getLogger(__name__)


class SceneAnalysisModelErrorCode(StrEnum):
    """Stable application error codes for model-backed scene analysis."""

    MODEL_OUTPUT_INVALID = "modelOutputInvalid"
    IMAGE_UNAVAILABLE = "imageUnavailable"
    IMAGE_INVALID = "imageInvalid"
    IMAGE_REJECTED = "imageModerationFailed"


class SceneAnalysisModelError(SceneAnalysisError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def build_scene_analysis_schema() -> dict[str, Any]:
    """Strict JSON schema for the shared scene-analysis output contract."""
    return build_strict_json_schema(SceneAnalysisModelResult)


class UploadedSceneAnalyzer:
    """Traces one uploaded-image analysis through the vision seam."""

    def __init__(
        self,
        storage: ImageStorage,
        client: VisionModelClient,
        config: VisionModelConfig,
        *,
        tracer: AITracer,
        provider: str,
        object_grounder: ObjectGrounder | None = None,
        image_moderator: ImageModerator | None = None,
    ) -> None:
        self._storage = storage
        self._client = client
        self._config = config
        self._tracer = tracer
        self._provider = provider
        self._object_grounder = object_grounder
        self._image_moderator = image_moderator
        self._json_schema = build_scene_analysis_schema()

    def analyze(
        self,
        session: Session,
        asset: MediaAsset,
        profile: Mapping[str, Any],
        scene: Mapping[str, Any] | None,
    ) -> SceneAnalysisResult:
        del profile, scene
        with self._tracer.trace(
            "scene-analysis",
            session_id=str(session.id),
            feature=AiFeature.SCENE_ANALYSIS.value,
            metadata={"assetSource": asset.source.value},
        ) as root:
            with self._tracer.span("image-retrieval") as retrieval:
                try:
                    data = self._storage.download(asset.storage_key)
                except Exception as error:
                    retrieval.update(
                        error_code=SceneAnalysisModelErrorCode.IMAGE_UNAVAILABLE.value
                    )
                    root.update(
                        error_code=SceneAnalysisModelErrorCode.IMAGE_UNAVAILABLE.value
                    )
                    raise SceneAnalysisModelError(
                        SceneAnalysisModelErrorCode.IMAGE_UNAVAILABLE,
                        "scene image could not be retrieved",
                    ) from error
                try:
                    image = VisionImage(data=data, mime_type=asset.mime_type)
                except VisionModelError as error:
                    retrieval.update(
                        error_code=SceneAnalysisModelErrorCode.IMAGE_INVALID.value
                    )
                    root.update(
                        error_code=SceneAnalysisModelErrorCode.IMAGE_INVALID.value
                    )
                    raise SceneAnalysisModelError(
                        SceneAnalysisModelErrorCode.IMAGE_INVALID,
                        "scene image is not usable",
                    ) from error
                retrieval.update(
                    metadata={
                        "imageByteCount": len(data),
                        "mimeType": asset.mime_type,
                    }
                )

            request = VisionModelRequest(
                image=image,
                system_prompt=SCENE_ANALYSIS_SYSTEM_PROMPT,
                user_instruction=SCENE_ANALYSIS_USER_INSTRUCTION,
                json_schema_name="scene_analysis_v2",
                json_schema=self._json_schema,
                prompt_version=SCENE_ANALYSIS_PROMPT_VERSION,
            )

            moderation_executor = None
            moderation_future = None
            if self._image_moderator is not None:
                moderation_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1
                )
                moderation_future = moderation_executor.submit(
                    self._image_moderator.moderate, image
                )

            attempts = 1 + self._config.max_retries
            attempts_used = 0
            try:
                for attempt in range(1, attempts + 1):
                    attempts_used = attempt
                    try:
                        with self._tracer.generation(
                            "scene-analysis-generation",
                            feature=AiFeature.SCENE_ANALYSIS.value,
                            provider=self._provider,
                            model=self._config.model_name,
                            prompt_version=SCENE_ANALYSIS_PROMPT_VERSION,
                            schema_version=SCENE_ANALYSIS_SCHEMA_VERSION,
                            model_parameters={
                                "maxOutputTokens": self._config.max_output_tokens,
                                "timeoutSeconds": self._config.timeout_seconds,
                            },
                            metadata={"attempt": attempt},
                        ) as generation:
                            try:
                                response = self._client.generate(request)
                            except VisionModelError as error:
                                generation.update(
                                    error_code=error.code.value,
                                    retry_count=attempt - 1,
                                )
                                raise
                            generation.update(
                                input_tokens=response.input_tokens,
                                output_tokens=response.output_tokens,
                            )

                        with self._tracer.span(
                            "output-validation", metadata={"attempt": attempt}
                        ) as validation:
                            try:
                                parsed = parse_scene_analysis(response.output_text)
                            except SceneAnalysisValidationError as error:
                                validation.update(
                                    validation_result="invalid",
                                    error_code=",".join(
                                        sorted(
                                            {
                                                issue.code.value
                                                for issue in error.issues
                                            }
                                        )
                                    ),
                                )
                                raise
                            validation.update(validation_result="valid")

                        with self._tracer.span("result-mapping") as mapping_span:
                            domain = model_result_to_domain(session, parsed)
                            mapping_span.update(
                                metadata={
                                    "objectCount": len(domain.objects),
                                    "relationCount": len(domain.relations),
                                    "modelObjectCount": len(parsed.objects),
                                }
                            )
                        if self._object_grounder is not None:
                            with self._tracer.span("object-grounding") as grounding:
                                try:
                                    domain = apply_object_grounding(
                                        domain, image, self._object_grounder
                                    )
                                except ObjectGroundingError as error:
                                    logger.warning("object grounding failed", exc_info=error)
                                    grounding.update(
                                        error_code="objectGroundingUnavailable"
                                    )
                                else:
                                    grounding.update(
                                        metadata={"objectCount": len(domain.objects)}
                                    )
                        if moderation_future is not None:
                            with self._tracer.span(
                                "image-moderation"
                            ) as moderation:
                                try:
                                    verdict = moderation_future.result()
                                except ImageModerationError as error:
                                    logger.warning(
                                        "image moderation failed", exc_info=error
                                    )
                                    moderation.update(
                                        error_code="imageModerationUnavailable"
                                    )
                                else:
                                    moderation.update(
                                        metadata={
                                            "flagged": verdict.flagged,
                                            "categories": list(verdict.categories),
                                        }
                                    )
                                    if verdict.flagged:
                                        moderation.update(
                                            error_code=(
                                                SceneAnalysisModelErrorCode
                                                .IMAGE_REJECTED.value
                                            )
                                        )
                                        root.update(
                                            error_code=(
                                                SceneAnalysisModelErrorCode
                                                .IMAGE_REJECTED.value
                                            )
                                        )
                                        raise SceneAnalysisModelError(
                                            SceneAnalysisModelErrorCode.IMAGE_REJECTED,
                                            "scene image was rejected by moderation",
                                        )
                        root.update(
                            retry_count=attempts_used - 1, validation_result="valid"
                        )
                        return domain
                    except VisionModelError as error:
                        retryable = error.transient or (
                            error.code is VisionModelErrorCode.PROVIDER_RESPONSE_INVALID
                        )
                        if retryable and attempt < attempts:
                            logger.warning(
                                "scene analysis attempt failed, retrying",
                                extra={"attempt": attempt, "code": error.code.value},
                            )
                            continue
                        root.update(
                            retry_count=attempts_used - 1,
                            validation_result="invalid",
                            error_code=error.code.value,
                        )
                        if error.code is VisionModelErrorCode.PROVIDER_RESPONSE_INVALID:
                            raise SceneAnalysisModelError(
                                SceneAnalysisModelErrorCode.MODEL_OUTPUT_INVALID,
                                "scene analysis model returned invalid output",
                            ) from error
                        raise SceneAnalysisModelError(error.code.value, str(error)) from error
                    except SceneAnalysisValidationError as error:
                        if attempt < attempts:
                            logger.warning(
                                "scene analysis output failed validation, retrying",
                                extra={"attempt": attempt},
                            )
                            continue
                        root.update(
                            retry_count=attempts_used - 1,
                            validation_result="invalid",
                            error_code=(
                                SceneAnalysisModelErrorCode.MODEL_OUTPUT_INVALID.value
                            ),
                        )
                        raise SceneAnalysisModelError(
                            SceneAnalysisModelErrorCode.MODEL_OUTPUT_INVALID,
                            "scene analysis model returned output that failed validation",
                        ) from error

            finally:
                if moderation_executor is not None:
                    moderation_executor.shutdown(wait=False)

            root.update(
                retry_count=attempts_used - 1, validation_result="invalid"
            )
            raise SceneAnalysisModelError(
                SceneAnalysisModelErrorCode.MODEL_OUTPUT_INVALID,
                "scene analysis model returned invalid output",
            )


class RoutedSceneAnalyzer:
    """Keep curated scenes deterministic; send only user images to the model."""

    def __init__(self, curated: Any, uploaded: Any) -> None:
        self.curated = curated
        self.uploaded = uploaded

    def analyze(self, session, asset, profile, scene) -> SceneAnalysisResult:
        analyzer = self.curated if asset.source == "preloaded" else self.uploaded
        return analyzer.analyze(session, asset, profile, scene)
