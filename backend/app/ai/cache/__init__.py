"""Validated feature-result cache shared app-wide through ``AiRuntime``."""

from app.ai.cache.cache import (
    CacheRequest,
    CacheWaitTimeout,
    FeatureVersion,
    Generated,
    ResultCache,
)
from app.ai.cache.features import generated, run_cached
from app.ai.cache.references import ReferenceMap
from app.ai.cache.store import (
    CacheEntry,
    CacheScope,
    CacheStore,
    InMemoryCacheStore,
    Provenance,
)
from app.ai.cache.templates import (
    GENERATED_CONTENT_KEY,
    TEMPLATE_ARTIFACT_VERSION,
    Template,
    TemplateMissing,
    TemplateSet,
    template_fingerprint,
)

__all__ = [
    "GENERATED_CONTENT_KEY",
    "TEMPLATE_ARTIFACT_VERSION",
    "CacheEntry",
    "CacheRequest",
    "CacheScope",
    "CacheStore",
    "CacheWaitTimeout",
    "FeatureVersion",
    "Generated",
    "InMemoryCacheStore",
    "Provenance",
    "ReferenceMap",
    "ResultCache",
    "Template",
    "TemplateMissing",
    "TemplateSet",
    "generated",
    "run_cached",
    "template_fingerprint",
]
