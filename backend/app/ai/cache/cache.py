"""Validated-result cache with single-flight deduplication of concurrent misses.

Only results that passed feature validation are stored. A hit is mapped back
onto the current payload's references and validated again before use, and is
rejected if its deployment is no longer approved for the route. Concurrent
misses for one key share a single generation; if it fails, every waiter gets
that failure and uses its usual fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.ai.cache.references import ReferenceMap
from app.ai.cache.store import CacheEntry, CacheScope, CacheStore, InMemoryCacheStore, Provenance
from app.ai.observability import AITracer, NoOpAITracer

logger = logging.getLogger(__name__)

Clock = Callable[[], float]


@dataclass(frozen=True)
class FeatureVersion:
    feature: str
    prompt_version: str
    schema_version: str
    validator_version: str


@dataclass(frozen=True)
class Generated[T]:
    """A freshly validated result and the deployment that served it."""

    result: T
    deployment_id: str | None
    model: str | None


@dataclass(frozen=True)
class CacheRequest[T]:
    version: FeatureVersion
    scope: CacheScope | None
    """``None`` bypasses the cache: no lookup and no write."""
    payload: Mapping[str, Any]
    generation: Any
    """JSON-serializable generation settings of every deployment the route allows."""
    approved_deployments: frozenset[str]
    compute: Callable[[], Generated[T]]
    encode: Callable[[T], Any]
    decode: Callable[[Any], T]
    """Rebuilds and revalidates a result against the current payload; raises if invalid."""
    wait_seconds: float | None = None


class CacheWaitTimeout(TimeoutError):
    """A concurrent generation for the same key did not finish in time."""


@dataclass
class _Flight:
    done: threading.Event = field(default_factory=threading.Event)
    value: str | None = None
    references: ReferenceMap | None = None
    error: BaseException | None = None


class ResultCache:
    def __init__(
        self,
        store: CacheStore | None = None,
        *,
        ttl_seconds: float = 86_400,
        max_entries: int = 2_000,
        enabled: bool = True,
        clock: Clock = time.time,
        tracer: AITracer | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.enabled = enabled
        self._store = store if store is not None else InMemoryCacheStore(max_entries)
        self._ttl = ttl_seconds
        self._clock = clock
        self._tracer = tracer or NoOpAITracer()
        self._flights: dict[str, _Flight] = {}
        self._lock = threading.Lock()

    @property
    def in_flight(self) -> int:
        return len(self._flights)

    def invalidate(
        self, *, feature: str | None = None, scope: CacheScope | None = None
    ) -> int:
        """Drop entries matching every given filter; returns how many."""
        return self._store.invalidate(
            lambda entry: (feature is None or entry.feature == feature)
            and (scope is None or entry.scope == scope)
        )

    def clear(self) -> int:
        return self._store.invalidate(lambda _entry: True)

    def get_or_generate[T](self, request: CacheRequest[T]) -> T:
        if not self.enabled or request.scope is None:
            return request.compute().result
        references = ReferenceMap(request.payload)
        key = self._key(request, references)
        with self._tracer.span(
            "result-cache", metadata={"feature": request.version.feature}
        ) as span:
            cached = self._hit(key, request, references)
            if cached is not None:
                span.update(metadata={"outcome": "hit"})
                return cached
            with self._lock:
                flight = self._flights.get(key)
                leader = flight is None
                if leader:
                    flight = self._flights[key] = _Flight()
            if not leader:
                span.update(metadata={"outcome": "shared"})
                return self._follow(flight, request, references)
            span.update(metadata={"outcome": "miss"})
            return self._lead(key, flight, request, references)

    def _key(self, request: CacheRequest, references: ReferenceMap) -> str:
        material = {
            "version": request.version.__dict__,
            "scope": request.scope.owner,
            "generation": request.generation,
            "payload": references.canonical_payload(request.payload),
        }
        text = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()

    def _hit[T](
        self, key: str, request: CacheRequest[T], references: ReferenceMap
    ) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock():
            self._store.delete(key)
            return None
        if entry.provenance.deployment_id not in request.approved_deployments:
            logger.info(
                "Dropping cached %s result from unapproved deployment.",
                request.version.feature,
            )
            self._store.delete(key)
            return None
        try:
            return request.decode(references.from_aliases(json.loads(entry.value)))
        except Exception:
            logger.warning(
                "Dropping cached %s result that failed revalidation.",
                request.version.feature,
            )
            self._store.delete(key)
            return None

    def _lead[T](
        self,
        key: str,
        flight: _Flight,
        request: CacheRequest[T],
        references: ReferenceMap,
    ) -> T:
        try:
            # Another flight may have completed after our initial lookup but
            # before we registered leadership. Publish that hit to our waiters.
            cached = self._hit(key, request, references)
            if cached is not None:
                flight.value = json.dumps(request.encode(cached), ensure_ascii=False)
                flight.references = references
                return cached
            generated = request.compute()
            encoded = request.encode(generated.result)
            # Sharing a successful generation does not depend on eligibility
            # for persistent storage. JSON also isolates each waiter's result.
            flight.value = json.dumps(encoded, ensure_ascii=False)
            flight.references = references
            self._store_result(key, request, references, generated, encoded)
            return generated.result
        except BaseException as error:
            flight.error = error
            raise
        finally:
            with self._lock:
                flight.done.set()
                self._flights.pop(key, None)

    def _store_result[T](
        self,
        key: str,
        request: CacheRequest[T],
        references: ReferenceMap,
        generated: Generated[T],
        encoded: Any,
    ) -> None:
        if generated.deployment_id not in request.approved_deployments:
            return
        aliased = references.to_aliases(encoded)
        if aliased is None:
            return
        value = json.dumps(aliased, ensure_ascii=False)
        now = self._clock()
        version = request.version
        self._store.put(
            key,
            CacheEntry(
                feature=version.feature,
                scope=request.scope,
                value=value,
                provenance=Provenance(
                    deployment_id=generated.deployment_id,
                    model=generated.model or "",
                    prompt_version=version.prompt_version,
                    schema_version=version.schema_version,
                    validator_version=version.validator_version,
                    created_at=now,
                ),
                expires_at=now + self._ttl,
            ),
        )

    def _follow[T](self, flight: _Flight, request: CacheRequest[T], references: ReferenceMap) -> T:
        if not flight.done.wait(request.wait_seconds):
            raise CacheWaitTimeout(f"{request.version.feature} generation still running")
        if flight.error is not None:
            raise flight.error
        assert flight.value is not None and flight.references is not None
        shared = flight.references.remap(json.loads(flight.value), references)
        return request.decode(shared)
