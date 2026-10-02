"""Scene-analysis feature package: one prompt, one schema, one validator."""

from app.ai.features.scene_analysis.mapping import (
    MIN_OBJECT_CONFIDENCE,
    MIN_RELATION_CONFIDENCE,
    model_result_to_domain,
)
from app.ai.features.scene_analysis.prompt import (
    SCENE_ANALYSIS_PROMPT_VERSION,
    SCENE_ANALYSIS_SCHEMA_VERSION,
    SCENE_ANALYSIS_SYSTEM_PROMPT,
    SCENE_ANALYSIS_USER_INSTRUCTION,
)
from app.ai.features.scene_analysis.schemas import (
    ModelAnchorPoint,
    ModelBoundingBox,
    ModelSceneAttribute,
    ModelSceneObject,
    ModelSceneRelation,
    SceneAnalysisIssue,
    SceneAnalysisIssueCode,
    SceneAnalysisModelResult,
    SceneAttributeType,
)
from app.ai.features.scene_analysis.service import (
    RoutedSceneAnalyzer,
    SceneAnalysisModelError,
    SceneAnalysisModelErrorCode,
    UploadedSceneAnalyzer,
    build_scene_analysis_schema,
)
from app.ai.features.scene_analysis.validation import (
    SceneAnalysisValidationError,
    parse_scene_analysis,
    validate_scene_analysis,
)

__all__ = [
    "MIN_OBJECT_CONFIDENCE",
    "MIN_RELATION_CONFIDENCE",
    "ModelAnchorPoint",
    "ModelBoundingBox",
    "ModelSceneAttribute",
    "ModelSceneObject",
    "ModelSceneRelation",
    "RoutedSceneAnalyzer",
    "SCENE_ANALYSIS_PROMPT_VERSION",
    "SCENE_ANALYSIS_SCHEMA_VERSION",
    "SCENE_ANALYSIS_SYSTEM_PROMPT",
    "SCENE_ANALYSIS_USER_INSTRUCTION",
    "SceneAnalysisIssue",
    "SceneAnalysisIssueCode",
    "SceneAnalysisModelError",
    "SceneAnalysisModelErrorCode",
    "SceneAnalysisModelResult",
    "SceneAnalysisValidationError",
    "SceneAttributeType",
    "UploadedSceneAnalyzer",
    "build_scene_analysis_schema",
    "model_result_to_domain",
    "parse_scene_analysis",
    "validate_scene_analysis",
]
