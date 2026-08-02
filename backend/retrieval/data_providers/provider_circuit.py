"""Per-provider circuit breakers for retrieval (v3).

After N consecutive failures a provider is disabled for a cool-down window
so hung/dead upstreams cannot stall every /v1/ask.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from backend.config import settings
from backend.core.logger import get_logger
from backend.production.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
)

logger = get_logger(__name__)

_breakers: dict[str, CircuitBreaker] = {}
_lock = threading.RLock()
_last_failure_reason: dict[str, str] = {}
_next_retry_at: dict[str, float] = {}


def _threshold() -> int:
    return int(getattr(settings, "RETRIEVAL_CIRCUIT_FAILURE_THRESHOLD", 3) or 3)


def _open_seconds() -> float:
    return float(getattr(settings, "RETRIEVAL_CIRCUIT_OPEN_SECONDS", 1800.0) or 1800.0)


def get_provider_breaker(provider_name: str) -> CircuitBreaker:
    name = f"retrieval:{provider_name}"
    with _lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                CircuitBreakerConfig(
                    name=name,
                    failure_threshold=_threshold(),
                    recovery_timeout_seconds=_open_seconds(),
                    half_open_success_threshold=1,
                )
            )
        return _breakers[name]


def is_provider_available(provider_name: str) -> bool:
    breaker = get_provider_breaker(provider_name)
    state = breaker.state
    return state != CircuitState.OPEN


def record_provider_success(provider_name: str) -> None:
    breaker = get_provider_breaker(provider_name)
    breaker._on_success()  # noqa: SLF001 — intentional internal hook
    with _lock:
        _last_failure_reason.pop(provider_name, None)
        _next_retry_at.pop(provider_name, None)


def record_provider_failure(provider_name: str, reason: str) -> None:
    breaker = get_provider_breaker(provider_name)
    breaker._on_failure()  # noqa: SLF001
    open_s = _open_seconds()
    with _lock:
        _last_failure_reason[provider_name] = reason
        snap = breaker.snapshot()
        if snap.get("state") == CircuitState.OPEN.value:
            _next_retry_at[provider_name] = time.time() + open_s
            logger.warning(
                "Retrieval provider circuit opened",
                extra={
                    "provider": provider_name,
                    "reason": reason,
                    "next_retry_in_s": open_s,
                    "failure_count": snap.get("failure_count"),
                },
            )


def provider_circuit_status(provider_name: str) -> dict[str, Any]:
    breaker = get_provider_breaker(provider_name)
    snap = breaker.snapshot()
    with _lock:
        next_retry = _next_retry_at.get(provider_name)
        reason = _last_failure_reason.get(provider_name)
    return {
        "provider": provider_name,
        "state": snap.get("state"),
        "failure_count": snap.get("failure_count"),
        "failure_reason": reason,
        "next_retry_at": next_retry,
        "next_retry_in_s": max(0.0, (next_retry or 0) - time.time()) if next_retry else 0.0,
    }


def reset_provider_circuits() -> None:
    with _lock:
        for b in _breakers.values():
            b.reset()
        _breakers.clear()
        _last_failure_reason.clear()
        _next_retry_at.clear()


__all__ = [
    "CircuitOpenError",
    "get_provider_breaker",
    "is_provider_available",
    "record_provider_success",
    "record_provider_failure",
    "provider_circuit_status",
    "reset_provider_circuits",
]
