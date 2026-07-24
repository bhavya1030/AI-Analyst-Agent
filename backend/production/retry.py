"""Retry policies for resilient external / pipeline calls."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from backend.production.logging import get_production_logger
from backend.production.metrics import get_metrics_collector

logger = get_production_logger("backend.production.retry")

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Exponential backoff retry policy."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 2.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple[type[BaseException], ...] = (Exception,)
    name: str = "default"

    def delay_for_attempt(self, attempt: int) -> float:
        """attempt is 1-based after a failure."""
        delay = self.base_delay_seconds * (self.exponential_base ** max(0, attempt - 1))
        delay = min(delay, self.max_delay_seconds)
        if self.jitter:
            delay = delay * (0.5 + random.random())
        return delay


def retry_call(
    fn: Callable[[], T],
    policy: RetryPolicy | None = None,
    *,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """
    Execute fn with retries.

    Records retries on the global metrics collector.
    """
    policy = policy or RetryPolicy()
    last_exc: Optional[BaseException] = None
    attempts = max(1, int(policy.max_attempts))

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except policy.retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= attempts:
                get_metrics_collector().incr("failures")
                get_metrics_collector().incr("retries", attempt - 1)
                logger.warning(
                    "Retry exhausted",
                    extra={
                        "policy": policy.name,
                        "attempts": attempt,
                        "error": str(exc),
                    },
                )
                raise
            get_metrics_collector().incr("retries")
            if on_retry:
                on_retry(attempt, exc)
            delay = policy.delay_for_attempt(attempt)
            logger.info(
                "Retrying after failure",
                extra={
                    "policy": policy.name,
                    "attempt": attempt,
                    "delay": delay,
                    "error": str(exc),
                },
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


class Retryable:
    """Decorator-style wrapper."""

    def __init__(self, policy: RetryPolicy | None = None):
        self.policy = policy or RetryPolicy()

    def __call__(self, fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return retry_call(lambda: fn(*args, **kwargs), self.policy)

        wrapper.__name__ = getattr(fn, "__name__", "retryable")
        return wrapper
