"""Error mapping and logging shared by every provider adapter.

Errors and logs carry stable codes, HTTP status, retry hints and scalar call
facts only: never provider response bodies, prompts or API keys.
"""

from __future__ import annotations

import email.utils
import logging
import math
import time
from datetime import UTC, datetime
from typing import Any

from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope

logger = logging.getLogger("app.ai.adapters")

_STATUS_MESSAGES = {
    ProviderErrorCode.PROVIDER_TIMEOUT: "timed out",
    ProviderErrorCode.PROVIDER_AUTH: "authentication failed",
    ProviderErrorCode.PROVIDER_RATE_LIMITED: "rate limited",
    ProviderErrorCode.PROVIDER_UNAVAILABLE: "unavailable",
}


def status_error(status_code: int | None) -> tuple[ProviderErrorCode, ProviderFailureScope]:
    """The provider-neutral meaning of an HTTP error status."""
    if status_code in (401, 403):
        return ProviderErrorCode.PROVIDER_AUTH, ProviderFailureScope.CREDENTIALS
    if status_code == 404:
        return ProviderErrorCode.PROVIDER_ERROR, ProviderFailureScope.MODEL
    if status_code == 429:
        return ProviderErrorCode.PROVIDER_RATE_LIMITED, ProviderFailureScope.QUOTA
    if status_code is not None and (status_code == 408 or status_code >= 500):
        return ProviderErrorCode.PROVIDER_UNAVAILABLE, ProviderFailureScope.SERVICE
    return ProviderErrorCode.PROVIDER_ERROR, ProviderFailureScope.REQUEST


def status_message(label: str, code: ProviderErrorCode) -> str:
    return f"{label} {_STATUS_MESSAGES.get(code, 'request failed')}"


def _finite_seconds(value: float) -> float | None:
    return max(0.0, value) if math.isfinite(value) else None


def parse_retry_after(headers: Any) -> float | None:
    """Seconds to wait from ``Retry-After`` (seconds or HTTP date) or ``retry-after-ms``."""
    if not headers:
        return None
    try:
        values = {str(key).lower(): str(value) for key, value in headers.items()}
    except (AttributeError, TypeError):
        return None
    if milliseconds := values.get("retry-after-ms"):
        try:
            return _finite_seconds(float(milliseconds) / 1000)
        except ValueError:
            pass
    value = values.get("retry-after")
    if not value:
        return None
    try:
        return _finite_seconds(float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def provider_error(
    code: ProviderErrorCode,
    message: str,
    *,
    kind: str,
    provider: str,
    endpoint: str,
    model: str,
    prompt_version: str,
    start: float,
    status_code: int | None = None,
    retry_after_seconds: float | None = None,
    scope: ProviderFailureScope | None = None,
) -> ProviderError:
    """Log one adapter failure and build the error to raise."""
    error = ProviderError(
        code,
        message,
        provider=provider,
        status_code=status_code,
        retry_after_seconds=retry_after_seconds,
        scope=scope,
    )
    latency_seconds = round(time.monotonic() - start, 3)
    logger.warning(
        "%s provider error: provider=%s model=%s endpoint=%s "
        "status_code=%s code=%s scope=%s retry_after_seconds=%s latency_seconds=%s",
        kind,
        provider,
        model,
        endpoint,
        status_code,
        code.value,
        error.scope.value,
        retry_after_seconds,
        latency_seconds,
        extra={
            "code": code.value,
            "scope": error.scope.value,
            "status_code": status_code,
            "retry_after_seconds": retry_after_seconds,
            "provider": provider,
            "endpoint": endpoint,
            "model": model,
            "prompt_version": prompt_version,
            "latency_seconds": latency_seconds,
        },
    )
    return error
