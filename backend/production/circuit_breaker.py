"""Circuit breaker for failing dependencies."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, TypeVar

from backend.production.logging import get_production_logger
from backend.production.metrics import get_metrics_collector

logger = get_production_logger("backend.production.circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"  # normal
    OPEN = "open"  # failing fast
    HALF_OPEN = "half_open"  # trial request allowed


class CircuitOpenError(RuntimeError):
    """Raised when circuit is open and calls are blocked."""


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_success_threshold: int = 1
    name: str = "default"


class CircuitBreaker:
    """
    Simple circuit breaker.

    CLOSED → (failures >= threshold) → OPEN
    OPEN → (timeout elapsed) → HALF_OPEN
    HALF_OPEN → success → CLOSED; failure → OPEN
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self._lock = threading.RLock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def call(self, fn: Callable[[], T]) -> T:
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                get_metrics_collector().incr("circuit_open_rejections")
                raise CircuitOpenError(
                    f"Circuit '{self.config.name}' is open; call rejected"
                )

        try:
            result = fn()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.half_open_success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        "Circuit closed after recovery",
                        extra={"circuit": self.config.name},
                    )
            else:
                self._failure_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            get_metrics_collector().incr("circuit_failures")
            if self._state == CircuitState.HALF_OPEN:
                self._trip()
            elif self._failure_count >= self.config.failure_threshold:
                self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._success_count = 0
        get_metrics_collector().incr("circuit_opens")
        logger.warning(
            "Circuit opened",
            extra={
                "circuit": self.config.name,
                "failures": self._failure_count,
            },
        )

    def _maybe_transition_to_half_open(self) -> None:
        if self._state != CircuitState.OPEN:
            return
        if time.monotonic() - self._opened_at >= self.config.recovery_timeout_seconds:
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info(
                "Circuit half-open",
                extra={"circuit": self.config.name},
            )

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._maybe_transition_to_half_open()
            return {
                "name": self.config.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
            }


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str = "default", **kwargs: Any) -> CircuitBreaker:
    with _breakers_lock:
        if name not in _breakers:
            cfg = CircuitBreakerConfig(name=name, **kwargs)
            _breakers[name] = CircuitBreaker(cfg)
        return _breakers[name]


def reset_circuit_breakers() -> None:
    with _breakers_lock:
        for b in _breakers.values():
            b.reset()
        _breakers.clear()
