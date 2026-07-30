"""Budgeted execution for forecasting (never hang the HTTP request)."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from backend.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class BudgetResult:
    value: Any = None
    timed_out: bool = False
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


def run_with_budget(
    fn: Callable[[], T],
    *,
    budget_seconds: float,
    label: str = "forecast",
) -> BudgetResult:
    """
    Run ``fn`` in a worker thread with a hard wall-clock budget.

    On timeout, returns timed_out=True (worker may still finish in background;
    we do not join beyond the budget so the request can return).
    """
    import time

    budget = max(0.5, float(budget_seconds or 10.0))
    t0 = time.perf_counter()
    # Small functions: run inline if budget is generous enough for expected fast path
    # Always use executor for isolation of slow models (Prophet/ARIMA).
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="fc-budget")
    try:
        future = executor.submit(fn)
        try:
            value = future.result(timeout=budget)
            return BudgetResult(
                value=value,
                timed_out=False,
                elapsed_seconds=time.perf_counter() - t0,
            )
        except concurrent.futures.TimeoutError:
            logger.warning(
                "Forecast budget exceeded",
                extra={"label": label, "budget_seconds": budget},
            )
            # Do not wait for the slow worker; abandon the future.
            future.cancel()
            return BudgetResult(
                value=None,
                timed_out=True,
                elapsed_seconds=time.perf_counter() - t0,
                error=f"Forecast budget of {budget:.1f}s exceeded during {label}",
            )
        except Exception as exc:
            return BudgetResult(
                value=None,
                timed_out=False,
                elapsed_seconds=time.perf_counter() - t0,
                error=str(exc),
            )
    finally:
        # shutdown(wait=False) so timeout path never blocks the request
        executor.shutdown(wait=False, cancel_futures=True)
