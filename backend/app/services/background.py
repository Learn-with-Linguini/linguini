"""Seam for running work off the HTTP request path."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

logger = logging.getLogger(__name__)


class BackgroundRunner(Protocol):
    def submit(self, fn, /, *args, **kwargs) -> None: ...


class InlineBackgroundRunner:
    """Runs the job synchronously; the default for tests and offline deploys."""

    def submit(self, fn, /, *args, **kwargs) -> None:
        fn(*args, **kwargs)

    def shutdown(self, wait: bool = True) -> None:
        return None


class ThreadPoolBackgroundRunner:
    def __init__(self, max_workers: int | None = None):
        workers = max_workers or int(
            os.getenv("BACKGROUND_WORKERS", "4").strip() or "4"
        )
        self._pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="background-runner"
        )

    def _report(self, future) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Background job failed.")

    def submit(self, fn, /, *args, **kwargs) -> None:
        self._pool.submit(fn, *args, **kwargs).add_done_callback(self._report)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)
