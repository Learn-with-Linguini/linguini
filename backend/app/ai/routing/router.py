"""Routed text and vision clients behind the existing model contracts.

A route lists deployments in priority order. Each call leases a credential
from the deployment's round-robin pool, builds or reuses the immutable client
for that deployment and credential, and makes one outbound request. Eligible
transient failures move on within the invocation's call budget and
deadline; refusals and request or schema errors stop immediately, and
invalid model output goes back to the feature's own repair step.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from app.ai.contracts.config import ModelConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.metadata import RouteInfo
from app.ai.observability import AITracer, NoOpAITracer
from app.ai.pool import ClientCache, CredentialLease
from app.ai.routing.invocation import Clock, InvocationContext

_DEPLOYMENT_SCOPES = frozenset({ProviderFailureScope.SERVICE, ProviderFailureScope.MODEL})


def fails_over(error: ProviderError) -> bool:
    """Whether another credential or deployment may still serve the call."""
    if error.transient:
        return True
    if error.code is ProviderErrorCode.PROVIDER_AUTH:
        return error.scope is ProviderFailureScope.CREDENTIALS
    return error.scope in (ProviderFailureScope.QUOTA, ProviderFailureScope.MODEL)


class CredentialSource(Protocol):
    def acquire(
        self, deployment_id: str, exclude: frozenset[str] = frozenset()
    ) -> CredentialLease: ...

    def report_success(self, lease: CredentialLease) -> None: ...

    def report_failure(self, lease: CredentialLease, error: ProviderError) -> None: ...


class FixedCredential:
    """One implicit credential with no shared health, for a directly built client."""

    CREDENTIAL_ID = "direct"

    def acquire(
        self, deployment_id: str, exclude: frozenset[str] = frozenset()
    ) -> CredentialLease:
        if self.CREDENTIAL_ID in exclude:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_AUTH,
                f"no usable credential for deployment {deployment_id}",
                scope=ProviderFailureScope.CREDENTIALS,
            )
        return CredentialLease(deployment_id, self.CREDENTIAL_ID, self.CREDENTIAL_ID, "")

    def report_success(self, lease: CredentialLease) -> None:
        return None

    def report_failure(self, lease: CredentialLease, error: ProviderError) -> None:
        return None


@dataclass(frozen=True)
class RouteTarget:
    deployment_id: str
    provider: str
    config: ModelConfig
    build: Callable[[str], Any] = field(compare=False, repr=False)
    """Builds the immutable client for one credential secret, without I/O."""


def _deadline_error() -> ProviderError:
    return ProviderError(
        ProviderErrorCode.PROVIDER_TIMEOUT,
        "invocation deadline exceeded",
        scope=ProviderFailureScope.SERVICE,
    )


def _budget_error() -> ProviderError:
    return ProviderError(
        ProviderErrorCode.PROVIDER_ERROR,
        "invocation model-call budget exhausted",
        scope=ProviderFailureScope.REQUEST,
    )


class RoutedModelClient:
    """A ``TextModelClient`` or ``VisionModelClient`` that routes every call."""

    def __init__(
        self,
        kind: str,
        targets: Sequence[RouteTarget],
        credentials: CredentialSource,
        *,
        max_model_calls: int,
        deadline_seconds: float | None = None,
        clients: ClientCache | None = None,
        tracer: AITracer | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        if not targets:
            raise ValueError("a route needs at least one deployment")
        self._kind = kind
        self._targets = tuple(targets)
        self._credentials = credentials
        self._max_model_calls = max_model_calls
        self._deadline_seconds = deadline_seconds
        self._clients = clients or ClientCache()
        self._tracer = tracer or NoOpAITracer()
        self._clock = clock

    def __repr__(self) -> str:
        deployments = [target.deployment_id for target in self._targets]
        return f"RoutedModelClient(kind={self._kind!r}, deployments={deployments})"

    @property
    def max_duration_seconds(self) -> float:
        """Upper bound on one invocation, including failover and repair."""
        if self._deadline_seconds is not None:
            return self._deadline_seconds
        slowest = max(target.config.timeout_seconds for target in self._targets)
        return slowest * self._max_model_calls

    @property
    def approved_deployments(self) -> frozenset[str]:
        return frozenset(target.deployment_id for target in self._targets)

    @property
    def generation_settings(self) -> list[dict[str, Any]]:
        """Output-shaping settings of every deployment the route allows."""
        return [
            {
                "deployment": target.deployment_id,
                "provider": target.provider,
                "model": target.config.model_name,
                "temperature": target.config.temperature,
                "maxOutputTokens": target.config.max_output_tokens,
            }
            for target in self._targets
        ]

    def start_invocation(self) -> InvocationContext:
        return InvocationContext(
            self._max_model_calls,
            deadline_seconds=self._deadline_seconds,
            clock=self._clock,
        )

    def generate(self, request: Any, invocation: InvocationContext | None = None) -> Any:
        invocation = invocation or self.start_invocation()
        targets = self._targets
        exhausted: set[str] = set()
        excluded: dict[str, frozenset[str]] = {}
        last_error: ProviderError | None = None
        fallback_reason: str | None = None
        attempts = 0
        index = 0
        while len(exhausted) < len(targets):
            target = targets[index]
            if target.deployment_id in exhausted:
                index = (index + 1) % len(targets)
                continue
            remaining = invocation.remaining_seconds()
            if remaining is not None and remaining <= 0:
                raise last_error or _deadline_error()
            if not invocation.can_call():
                raise last_error or _budget_error()
            try:
                lease = self._credentials.acquire(
                    target.deployment_id, excluded.get(target.deployment_id, frozenset())
                )
            except ProviderError as unavailable:
                exhausted.add(target.deployment_id)
                last_error = last_error or unavailable
                fallback_reason = fallback_reason or unavailable.code.value
                index = (index + 1) % len(targets)
                continue
            if not invocation.consume():
                raise last_error or _budget_error()
            attempts += 1
            try:
                response = self._call(target, lease, request, remaining, attempts, fallback_reason)
            except ProviderError as error:
                if not fails_over(error):
                    raise
                last_error = error
                fallback_reason = error.code.value
                if error.scope is ProviderFailureScope.CREDENTIALS:
                    excluded[target.deployment_id] = excluded.get(
                        target.deployment_id, frozenset()
                    ) | {lease.credential_id}
                if error.scope in _DEPLOYMENT_SCOPES:
                    index = (index + 1) % len(targets)
                continue
            metadata = response.metadata
            return replace(
                response,
                route=RouteInfo(
                    deployment_id=target.deployment_id,
                    credential_id=lease.credential_id,
                    model=(metadata.model if metadata and metadata.model else None)
                    or target.config.model_name,
                    attempts=attempts,
                    fallback_reason=fallback_reason,
                ),
            )
        assert last_error is not None
        raise last_error

    def _call(
        self,
        target: RouteTarget,
        lease: CredentialLease,
        request: Any,
        remaining: float | None,
        attempt: int,
        fallback_reason: str | None,
    ) -> Any:
        key: Hashable = (self._kind, target.deployment_id, lease.credential_id, target.config)
        client = self._clients.get(key, lambda: target.build(lease.secret))
        attempt_metadata = {
            "deployment": target.deployment_id,
            "credentialId": lease.credential_id,
            "provider": target.provider,
            "requestedModel": target.config.model_name,
            "attempt": attempt,
        }
        if fallback_reason:
            attempt_metadata["fallbackReason"] = fallback_reason
        with self._tracer.span("model-call", metadata=attempt_metadata) as span:
            start = time.perf_counter()
            try:
                if remaining is not None and remaining < target.config.timeout_seconds:
                    response = client.generate(request, timeout_seconds=remaining)
                else:
                    response = client.generate(request)
            except ProviderError as error:
                self._credentials.report_failure(lease, error)
                span.update(
                    latency_ms=(time.perf_counter() - start) * 1000,
                    error_code=error.code.value,
                    metadata={
                        "scope": error.scope.value,
                        "statusCode": error.status_code,
                        "outcome": "failover" if fails_over(error) else "terminal",
                    },
                )
                raise
            self._credentials.report_success(lease)
            usage = response.metadata.usage if response.metadata else None
            span.update(
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=usage.total_tokens if usage else None,
                metadata={
                    "outcome": "success",
                    "servedModel": (
                        response.metadata.model if response.metadata else None
                    ) or target.config.model_name,
                },
            )
            return response


def as_routed(client: Any, config: ModelConfig, *, kind: str) -> RoutedModelClient:
    """Wrap a directly built or injected client as a one-deployment route.

    The budget matches the feature's own ``1 + max_retries`` calls and there
    is no shared health, so behaviour matches calling the client directly.
    """
    if isinstance(client, RoutedModelClient):
        return client
    return RoutedModelClient(
        kind,
        (RouteTarget("direct", "direct", config, lambda _secret: client),),
        FixedCredential(),
        max_model_calls=1 + config.max_retries,
    )


def route_metadata(response: Any) -> dict[str, Any]:
    """Secret-free trace fields describing which route served ``response``."""
    route = getattr(response, "route", None)
    if route is None:
        return {}
    fields = {
        "deployment": route.deployment_id,
        "credentialId": route.credential_id,
        "servedModel": route.model,
        "routeAttempts": route.attempts,
        "fallbackReason": route.fallback_reason,
    }
    return {key: value for key, value in fields.items() if value is not None}


def total_tokens(response: Any) -> int | None:
    metadata = getattr(response, "metadata", None)
    return metadata.usage.total_tokens if metadata is not None else None
