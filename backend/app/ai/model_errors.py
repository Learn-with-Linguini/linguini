"""Shared provider-error contract for all AI model adapters.

Adapters surface failures only through ``ProviderError``; callers map the
stable ``ProviderErrorCode`` onto feature-specific errors. Provider payload
text never travels inside these errors.
"""

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


_TRANSIENT_CODES = frozenset(
    {
        ProviderErrorCode.PROVIDER_TIMEOUT,
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        ProviderErrorCode.PROVIDER_RATE_LIMITED,
    }
)


class ProviderError(Exception):
    """Stable provider failure. Never carries provider payload text."""

    def __init__(self, code: ProviderErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)

    @property
    def transient(self) -> bool:
        return self.code in _TRANSIENT_CODES
