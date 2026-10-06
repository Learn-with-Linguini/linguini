"""Glue between feature services, their routed client and the result cache."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.ai.cache.cache import CacheRequest, FeatureVersion, Generated, ResultCache
from app.ai.cache.store import CacheScope

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
) -> T:
    """Serve ``payload`` from ``cache`` or ``compute`` it, sharing concurrent misses."""
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
            encode=lambda result: result.model_dump(mode="json", by_alias=True),
            decode=decode,
            wait_seconds=client.max_duration_seconds + _WAIT_MARGIN_SECONDS,
        )
    )
