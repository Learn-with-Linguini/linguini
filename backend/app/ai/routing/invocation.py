"""One logical model invocation: a deadline and a total outbound-call budget.

A feature opens one context per operation and passes it to every routed
call, so router failover and feature-owned validation repair draw on the
same budget and the same deadline.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

Clock = Callable[[], float]


class InvocationContext:
    def __init__(
        self,
        max_calls: int,
        *,
        deadline_seconds: float | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        self.max_calls = max_calls
        self._clock = clock
        self._deadline = None if deadline_seconds is None else clock() + deadline_seconds
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        """Outbound provider calls made so far."""
        return self._calls

    @property
    def retries(self) -> int:
        return max(0, self._calls - 1)

    def remaining_seconds(self) -> float | None:
        """Seconds left before the deadline, or ``None`` without one."""
        if self._deadline is None:
            return None
        return self._deadline - self._clock()

    def can_call(self) -> bool:
        remaining = self.remaining_seconds()
        return self._calls < self.max_calls and (remaining is None or remaining > 0)

    def consume(self) -> bool:
        """Take one call from the budget; ``False`` when none is left."""
        with self._lock:
            if self._calls >= self.max_calls:
                return False
            self._calls += 1
            return True
