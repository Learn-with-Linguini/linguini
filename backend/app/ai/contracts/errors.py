"""Shared provider-error contract for all AI model adapters.

Adapters surface failures only through ``ProviderError``; callers map the
stable ``ProviderErrorCode`` onto feature-specific errors. Provider payload
text and credentials never travel inside these errors.
"""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorCode(StrEnum):
    INVALID_IMAGE = "invalidImage"
    PROVIDER_TIMEOUT = "providerTimeout"
    PROVIDER_UNAVAILABLE = "providerUnavailable"
    PROVIDER_RATE_LIMITED = "providerRateLimited"
    PROVIDER_AUTH = "providerAuth"
    PROVIDER_REFUSED = "providerRefused"
    PROVIDER_RESPONSE_INVALID = "providerResponseInvalid"
    PROVIDER_ERROR = "providerError"


class ProviderFailureScope(StrEnum):
    """What a failure says about the next call, not just this one."""

    REQUEST = "request"
    """This request was rejected; a different request may succeed."""
    RESPONSE = "response"
    """The provider answered, but the output was refused or unusable."""
    MODEL = "model"
    """The model is unknown or unavailable to this key."""
    CREDENTIALS = "credentials"
    """The API key was rejected; every call with it will fail."""
    QUOTA = "quota"
    """Rate limit, quota or billing; calls may succeed after waiting."""
    SERVICE = "service"
    """The provider or network failed; the same call may succeed later."""


_TRANSIENT_CODES = frozenset(
    {
        ProviderErrorCode.PROVIDER_TIMEOUT,
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        ProviderErrorCode.PROVIDER_RATE_LIMITED,
    }
)

_DEFAULT_SCOPES = {
    ProviderErrorCode.INVALID_IMAGE: ProviderFailureScope.REQUEST,
    ProviderErrorCode.PROVIDER_TIMEOUT: ProviderFailureScope.SERVICE,
    ProviderErrorCode.PROVIDER_UNAVAILABLE: ProviderFailureScope.SERVICE,
    ProviderErrorCode.PROVIDER_RATE_LIMITED: ProviderFailureScope.QUOTA,
    ProviderErrorCode.PROVIDER_AUTH: ProviderFailureScope.CREDENTIALS,
    ProviderErrorCode.PROVIDER_REFUSED: ProviderFailureScope.RESPONSE,
    ProviderErrorCode.PROVIDER_RESPONSE_INVALID: ProviderFailureScope.RESPONSE,
    ProviderErrorCode.PROVIDER_ERROR: ProviderFailureScope.REQUEST,
}


class ProviderError(Exception):
    """Stable provider failure. Never carries provider payload text or keys."""

    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        scope: ProviderFailureScope | None = None,
    ) -> None:
        self.code = code
        self.provider = provider
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.scope = scope or _DEFAULT_SCOPES[code]
        super().__init__(message)

    @property
    def transient(self) -> bool:
        return self.code in _TRANSIENT_CODES
