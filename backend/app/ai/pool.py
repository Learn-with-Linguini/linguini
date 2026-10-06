"""Credential pool: thread-safe round-robin over healthy credentials.

Health is tracked separately for credentials, shared quota groups and
deployments. The pool lock guards only selection and state updates; model
calls always run outside it. Clients are immutable and cached per
deployment and credential, so no request ever changes a shared client's key
or model.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.ai.config.models import AiConfig
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope

Clock = Callable[[], float]


class HealthScope(StrEnum):
    CREDENTIAL = "credential"
    QUOTA_GROUP = "quotaGroup"
    DEPLOYMENT = "deployment"


class HealthReason(StrEnum):
    AUTH_FAILED = "authFailed"
    RATE_LIMITED = "rateLimited"
    QUOTA_EXHAUSTED = "quotaExhausted"
    MODEL_UNAVAILABLE = "modelUnavailable"
    SERVICE_UNAVAILABLE = "serviceUnavailable"


@dataclass(frozen=True)
class Health:
    disabled: bool = False
    cooldown_until: float = 0.0
    reason: HealthReason | None = None
    consecutive_failures: int = 0

    def available(self, now: float) -> bool:
        return not self.disabled and self.cooldown_until <= now


HEALTHY = Health()


class PoolState(Protocol):
    """Health and round-robin state. The pool serialises every access."""

    def get(self, scope: HealthScope, key: str) -> Health: ...

    def put(self, scope: HealthScope, key: str, health: Health) -> None: ...

    def cursor(self, deployment_id: str) -> int: ...

    def set_cursor(self, deployment_id: str, value: int) -> None: ...


class InMemoryPoolState:
    def __init__(self) -> None:
        self._health: dict[tuple[HealthScope, str], Health] = {}
        self._cursors: dict[str, int] = {}

    def get(self, scope: HealthScope, key: str) -> Health:
        return self._health.get((scope, key), HEALTHY)

    def put(self, scope: HealthScope, key: str, health: Health) -> None:
        if health == HEALTHY:
            self._health.pop((scope, key), None)
        else:
            self._health[(scope, key)] = health

    def cursor(self, deployment_id: str) -> int:
        return self._cursors.get(deployment_id, 0)

    def set_cursor(self, deployment_id: str, value: int) -> None:
        self._cursors[deployment_id] = value


@dataclass(frozen=True)
class CredentialLease:
    deployment_id: str
    credential_id: str
    quota_group: str
    secret: str = field(repr=False)


class CredentialPool:
    def __init__(
        self,
        config: AiConfig,
        secrets: Mapping[str, str],
        *,
        state: PoolState | None = None,
        clock: Clock = time.monotonic,
        rate_limit_cooldown_seconds: float = 10.0,
        quota_exhausted_cooldown_seconds: float = 300.0,
        deployment_cooldown_seconds: float = 30.0,
    ) -> None:
        self._config = config
        self._secrets = dict(secrets)
        self._state = state or InMemoryPoolState()
        self._clock = clock
        self._rate_limit_cooldown = rate_limit_cooldown_seconds
        self._quota_exhausted_cooldown = quota_exhausted_cooldown_seconds
        self._deployment_cooldown = deployment_cooldown_seconds
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"CredentialPool(deployments={sorted(self._config.deployments)})"

    def has_deployment(self, deployment_id: str) -> bool:
        return deployment_id in self._config.deployments

    def health(self, scope: HealthScope, key: str) -> Health:
        with self._lock:
            return self._state.get(scope, key)

    def acquire(self, deployment_id: str) -> CredentialLease:
        """Pick the next healthy credential, or raise without calling the provider."""
        deployment = self._config.deployments[deployment_id]
        provider = deployment.adapter.value
        ids = deployment.credentials
        with self._lock:
            now = self._clock()
            deployment_health = self._state.get(HealthScope.DEPLOYMENT, deployment_id)
            if not deployment_health.available(now):
                raise ProviderError(
                    ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    f"deployment {deployment_id} is cooling down",
                    provider=provider,
                    retry_after_seconds=deployment_health.cooldown_until - now,
                    scope=(
                        ProviderFailureScope.MODEL
                        if deployment_health.reason is HealthReason.MODEL_UNAVAILABLE
                        else ProviderFailureScope.SERVICE
                    ),
                )
            start = self._state.cursor(deployment_id)
            waits: list[float] = []
            for offset in range(len(ids)):
                index = (start + offset) % len(ids)
                credential_id = ids[index]
                secret = self._secrets.get(credential_id)
                credential = self._state.get(HealthScope.CREDENTIAL, credential_id)
                if not secret or credential.disabled:
                    continue
                quota_group = self._config.credentials[credential_id].quota_group
                group = self._state.get(HealthScope.QUOTA_GROUP, quota_group)
                until = max(credential.cooldown_until, group.cooldown_until)
                if until > now:
                    waits.append(until - now)
                    continue
                self._state.set_cursor(deployment_id, (index + 1) % len(ids))
                return CredentialLease(deployment_id, credential_id, quota_group, secret)
        if waits:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_RATE_LIMITED,
                f"every credential for deployment {deployment_id} is cooling down",
                provider=provider,
                retry_after_seconds=min(waits),
                scope=ProviderFailureScope.QUOTA,
            )
        raise ProviderError(
            ProviderErrorCode.PROVIDER_AUTH,
            f"no usable credential for deployment {deployment_id}",
            provider=provider,
            scope=ProviderFailureScope.CREDENTIALS,
        )

    def report_success(self, lease: CredentialLease) -> None:
        with self._lock:
            current = self._state.get(HealthScope.DEPLOYMENT, lease.deployment_id)
            if current != HEALTHY and current.available(self._clock()):
                self._state.put(HealthScope.DEPLOYMENT, lease.deployment_id, HEALTHY)

    def report_failure(self, lease: CredentialLease, error: ProviderError) -> None:
        """Cool down or disable the scope the provider's error points at."""
        retry_after = error.retry_after_seconds
        with self._lock:
            now = self._clock()
            if error.code is ProviderErrorCode.PROVIDER_AUTH and (
                error.scope is ProviderFailureScope.CREDENTIALS
            ):
                self._state.put(
                    HealthScope.CREDENTIAL,
                    lease.credential_id,
                    Health(disabled=True, reason=HealthReason.AUTH_FAILED),
                )
            elif error.scope is ProviderFailureScope.QUOTA:
                if error.code is ProviderErrorCode.PROVIDER_RATE_LIMITED:
                    reason, default = HealthReason.RATE_LIMITED, self._rate_limit_cooldown
                else:
                    reason, default = HealthReason.QUOTA_EXHAUSTED, self._quota_exhausted_cooldown
                self._cool_down(
                    HealthScope.QUOTA_GROUP,
                    lease.quota_group,
                    now + (default if retry_after is None else retry_after),
                    reason,
                )
            elif error.scope in (ProviderFailureScope.SERVICE, ProviderFailureScope.MODEL):
                current = self._state.get(HealthScope.DEPLOYMENT, lease.deployment_id)
                until = current.cooldown_until
                if retry_after is not None:
                    until = max(until, now + retry_after)
                elif error.scope is ProviderFailureScope.MODEL:
                    until = max(until, now + self._deployment_cooldown)
                self._state.put(
                    HealthScope.DEPLOYMENT,
                    lease.deployment_id,
                    Health(
                        cooldown_until=until,
                        reason=(
                            HealthReason.MODEL_UNAVAILABLE
                            if error.scope is ProviderFailureScope.MODEL
                            else HealthReason.SERVICE_UNAVAILABLE
                        ),
                        consecutive_failures=current.consecutive_failures + 1,
                    ),
                )

    def _cool_down(
        self, scope: HealthScope, key: str, until: float, reason: HealthReason
    ) -> None:
        current = self._state.get(scope, key)
        if current.cooldown_until < until:
            self._state.put(scope, key, Health(cooldown_until=until, reason=reason))


class ClientCache:
    """Builds each immutable client once per key. Building never does network I/O."""

    def __init__(self) -> None:
        self._clients: dict[Hashable, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable, build: Callable[[], Any]) -> Any:
        client = self._clients.get(key)
        if client is not None:
            return client
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = build()
                self._clients[key] = client
            return client


@dataclass(frozen=True)
class ProviderPool:
    credentials: CredentialPool
    clients: ClientCache = field(default_factory=ClientCache)

    @classmethod
    def from_settings(cls, settings: Any, **options: Any) -> ProviderPool:
        config = settings.ai_config or AiConfig(routes={})
        return cls(CredentialPool(config, settings.credential_secrets, **options))


class PooledModelClient:
    """Text or vision client that leases a credential for every call."""

    def __init__(
        self,
        pool: ProviderPool,
        kind: str,
        deployment_id: str,
        config: Hashable,
        factory: Callable[[str], Any],
    ) -> None:
        self._pool = pool
        self._kind = kind
        self._deployment_id = deployment_id
        self._config = config
        self._factory = factory

    def generate(self, request: Any) -> Any:
        lease = self._pool.credentials.acquire(self._deployment_id)
        client = self._pool.clients.get(
            (self._kind, self._deployment_id, lease.credential_id, self._config),
            lambda: self._factory(lease.secret),
        )
        try:
            response = client.generate(request)
        except ProviderError as error:
            self._pool.credentials.report_failure(lease, error)
            raise
        self._pool.credentials.report_success(lease)
        return response
