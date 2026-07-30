"""Per-provider and global retrieval budgets (Retrieval v3)."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class BudgetSnapshot:
    provider_timeout_s: float
    global_budget_s: float
    started_at: float
    used_s: float = 0.0

    @property
    def remaining_s(self) -> float:
        elapsed = time.perf_counter() - self.started_at
        return max(0.0, self.global_budget_s - elapsed)

    @property
    def exhausted(self) -> bool:
        return self.remaining_s <= 0.05

    def provider_wait_s(self) -> float:
        """Wait for a single provider search (min of per-provider and remaining global)."""
        return max(0.1, min(self.provider_timeout_s, self.remaining_s))

    def validation_wait_s(self) -> float:
        return max(0.1, min(self.provider_timeout_s, self.remaining_s))

    def mark(self) -> float:
        self.used_s = time.perf_counter() - self.started_at
        return self.used_s


def new_budget(
    *,
    provider_timeout_s: float | None = None,
    global_budget_s: float | None = None,
) -> BudgetSnapshot:
    return BudgetSnapshot(
        provider_timeout_s=float(
            provider_timeout_s
            if provider_timeout_s is not None
            else getattr(settings, "RETRIEVAL_PROVIDER_TIMEOUT_SECONDS", 5.0) or 5.0
        ),
        global_budget_s=float(
            global_budget_s
            if global_budget_s is not None
            else getattr(settings, "RETRIEVAL_GLOBAL_BUDGET_SECONDS", 12.0) or 12.0
        ),
        started_at=time.perf_counter(),
    )


def run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_s: float,
    label: str = "provider",
) -> tuple[Optional[T], bool, Optional[str], float]:
    """
    Run fn in a worker thread with a hard timeout.

    Returns (value, timed_out, error, elapsed_s).
    On timeout the worker is abandoned (cannot kill threads in CPython).
    """
    t0 = time.perf_counter()
    timeout = max(0.1, float(timeout_s))
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"ret-{label[:12]}"
    )
    try:
        future = executor.submit(fn)
        try:
            value = future.result(timeout=timeout)
            return value, False, None, time.perf_counter() - t0
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.warning(
                "Provider step timed out",
                extra={"label": label, "timeout_s": timeout},
            )
            return None, True, f"timeout:{timeout:.1f}s", time.perf_counter() - t0
        except Exception as exc:
            return None, False, str(exc), time.perf_counter() - t0
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def is_retryable_error(error: str | None) -> bool:
    """Retry only network/transient errors — never 404/401/403/HTML/login."""
    if not error:
        return False
    e = error.lower()
    # Non-retryable
    for needle in (
        "404",
        "401",
        "403",
        "html",
        "login",
        "blocked",
        "pdf",
        "not found",
        "unauthorized",
        "forbidden",
        "circuit_open",
        "metadata_only",
        "no_candidates",
    ):
        if needle in e:
            return False
    # Retryable network-ish
    for needle in (
        "timeout",
        "timed out",
        "connection",
        "reset",
        "temporarily",
        "503",
        "502",
        "504",
        "connectionreset",
        "connection aborted",
        "name resolution",
        "max retries",
        "read timed out",
        "connect timeout",
    ):
        if needle in e:
            return True
    return False
