"""Clients that sit between a production service and the real provider.

The feature services keep only the parsed result, so usage, latency and the
raw text would otherwise be lost. A recorder wraps the ``TextModelClient`` /
``VisionModelClient`` the service is given: the service's own prompt, schema
and validation run unchanged, and the recorder notes what came back.

Parameters (temperature, output cap) are set on the model config rather than
here, so a swept run differs from production only by that config.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.ai.model_errors import ProviderError, ProviderErrorCode

from .pricing import ModelFacts

RATE_LIMIT_RETRIES = 5
# Free-tier Gemini keys allow few requests per minute.
GEMINI_SLOTS = threading.Semaphore(3)


@dataclass(frozen=True)
class Overrides:
    """Model parameters varied in the sweep; None means "as production sends"."""

    temperature: float | None = None
    max_output_tokens: int | None = None

    def label(self) -> str:
        parts = [f"{k}={v}" for k, v in self.__dict__.items() if v is not None]
        return ",".join(parts) or "production"

    def applied_to(self, config: Any) -> Any:
        from dataclasses import replace

        changes = {k: v for k, v in self.__dict__.items() if v is not None}
        return replace(config, **changes) if changes else config


@dataclass
class CallRecord:
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    raw_text: str | None = None
    error: str | None = None
    error_code: str | None = None
    rate_limit_retries: int = 0
    applied: dict[str, Any] = field(default_factory=dict)


class RecordingClient:
    """Wraps a text or vision client; both expose ``generate(request)``."""

    def __init__(
        self, inner: Any, facts: ModelFacts, *, gemini: bool = False
    ) -> None:
        self.inner = inner
        self.facts = facts
        self.gemini = gemini
        self.record = CallRecord()

    def generate(self, request: Any) -> Any:
        """Retry only our own account's rate limits, which say nothing about the
        model. Every other failure, including provider overload, is raised to
        the service exactly as production would see it."""
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            started = time.perf_counter()
            try:
                if self.gemini:
                    with GEMINI_SLOTS:
                        response = self.inner.generate(request)
                else:
                    response = self.inner.generate(request)
            except ProviderError as error:
                self.record.latency_ms = (time.perf_counter() - started) * 1000
                if (
                    attempt < RATE_LIMIT_RETRIES
                    and error.code is ProviderErrorCode.PROVIDER_RATE_LIMITED
                ):
                    self.record.rate_limit_retries += 1
                    time.sleep(min(60, 8 * 2**attempt))
                    continue
                self.record.error = f"{error.code.value}: {error}"
                self.record.error_code = error.code.value
                raise
            except Exception as error:  # noqa: BLE001 - recorded, then re-raised
                self.record.latency_ms = (time.perf_counter() - started) * 1000
                self.record.error = f"{type(error).__name__}: {str(error)[:300]}"
                self.record.error_code = type(error).__name__
                raise
            self.record.latency_ms = (time.perf_counter() - started) * 1000
            self.record.input_tokens = response.input_tokens
            self.record.output_tokens = response.output_tokens
            self.record.raw_text = response.output_text
            if response.input_tokens is not None:
                self.record.cost_usd = self.facts.cost(
                    response.input_tokens, response.output_tokens or 0
                )
            return response
        raise AssertionError("unreachable")


class RecordingResponsesClient:
    """Recorder for the SDK-shaped I-Spy guess adapter (``responses.parse``)."""

    def __init__(self, inner: Any, facts: ModelFacts) -> None:
        self.inner = inner
        self.facts = facts
        self.record = CallRecord()
        self.responses = self

    def parse(self, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            response = self.inner.responses.parse(**kwargs)
        except Exception as error:  # noqa: BLE001 - recorded, then re-raised
            self.record.latency_ms = (time.perf_counter() - started) * 1000
            self.record.error = f"{type(error).__name__}: {str(error)[:300]}"
            self.record.error_code = type(error).__name__
            raise
        self.record.latency_ms = (time.perf_counter() - started) * 1000
        usage = getattr(response, "usage", None)
        self.record.input_tokens = getattr(usage, "input_tokens", None)
        self.record.output_tokens = getattr(usage, "output_tokens", None)
        parsed = getattr(response, "output_parsed", None)
        self.record.raw_text = (
            parsed.model_dump_json(by_alias=True) if parsed is not None else None
        )
        if self.record.input_tokens is not None:
            self.record.cost_usd = self.facts.cost(
                self.record.input_tokens, self.record.output_tokens or 0
            )
        return response
