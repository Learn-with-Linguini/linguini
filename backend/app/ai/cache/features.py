"""Glue between feature services, their routed client, scene templates and the cache."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.ai.cache.cache import CacheRequest, FeatureVersion, Generated, ResultCache
from app.ai.cache.store import CacheScope
from app.ai.cache.templates import TemplateMissing, TemplateSet

logger = logging.getLogger(__name__)

_WAIT_MARGIN_SECONDS = 5.0


def generated[T](result: T, response: Any) -> Generated[T]:
    route = getattr(response, "route", None)
    return Generated(
        result,
        route.deployment_id if route else None,
        route.model if route else None,
    )


def run_cached[T](
    cache: ResultCache | None,
    client: Any,
    *,
    version: FeatureVersion,
    scope: CacheScope | None,
    payload: dict[str, Any],
    compute: Callable[[], Generated[T]],
    decode: Callable[[Any], T],
    templates: TemplateSet | None = None,
) -> T:
    """Serve ``payload`` from a matching template, then ``cache``, else ``compute`` it.

    Concurrent cache misses share one ``compute``. Templates are revalidated
    with ``decode`` before use.
    """
    if templates is not None:
        reused = _from_template(templates, version, payload, decode)
        if reused is not None:
            return reused
        if not templates.generate:
            raise TemplateMissing(version.feature)
        compute = _recording(compute, templates, version, payload)
    if cache is None:
        return compute().result
    return cache.get_or_generate(
        CacheRequest(
            version=version,
            scope=scope,
            payload=payload,
            generation=client.generation_settings,
            approved_deployments=client.approved_deployments,
            compute=compute,
            encode=_encode,
            decode=decode,
            wait_seconds=client.max_duration_seconds + _WAIT_MARGIN_SECONDS,
        )
    )


def _encode(result: Any) -> Any:
    return result.model_dump(mode="json", by_alias=True)


def _from_template[T](
    templates: TemplateSet,
    version: FeatureVersion,
    payload: dict[str, Any],
    decode: Callable[[Any], T],
) -> T | None:
    data = templates.lookup(version, payload)
    if data is None:
        return None
    try:
        return decode(data)
    except Exception:
        logger.warning("Ignoring a %s scene template that failed revalidation.", version.feature)
        return None


def _recording[T](
    compute: Callable[[], Generated[T]],
    templates: TemplateSet,
    version: FeatureVersion,
    payload: dict[str, Any],
) -> Callable[[], Generated[T]]:
    def run() -> Generated[T]:
        generated = compute()
        templates.record(version, payload, generated, _encode)
        return generated

    return run
