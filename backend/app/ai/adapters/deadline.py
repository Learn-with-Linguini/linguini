"""Total call deadlines around cancellable I/O, without detached workers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.routing.invocation import InvocationContext

T = TypeVar("T")


class CallDeadline:
    def __init__(self, seconds: float, invocation: InvocationContext | None = None):
        self._expires = time.monotonic() + seconds
        self._invocation = invocation

    def remaining(self) -> float:
        remaining = self._expires - time.monotonic()
        if self._invocation is not None:
            shared = self._invocation.remaining_seconds()
            if shared is not None:
                remaining = min(remaining, shared)
        if remaining <= 0:
            raise TimeoutError("provider call deadline exceeded")
        return remaining

    def check(self) -> None:
        self.remaining()

    def begin_io(self) -> float:
        remaining = self.remaining()
        if self._invocation is not None and not self._invocation.consume():
            self.check()
            raise ProviderError(
                ProviderErrorCode.PROVIDER_ERROR,
                "invocation model-call budget exhausted",
                scope=ProviderFailureScope.REQUEST,
            )
        return remaining

    def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        async def execute() -> T:
            # Cancellation is delivered to the actual I/O task. The timeout
            # exits only after its finally blocks have closed the response.
            async with asyncio.timeout(self.remaining()):
                result = await operation()
            self.check()  # Also reject transports that suppress cancellation.
            return result

        self.check()
        return asyncio.run(execute())
