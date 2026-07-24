"""Token-bucket / sliding-window rate limiter."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Optional


class RateLimitExceeded(RuntimeError):
    """Raised when a request exceeds the configured rate limit."""


@dataclass
class RateLimitConfig:
    max_requests: int = 60
    window_seconds: float = 60.0
    name: str = "default"


class RateLimiter:
    """
    Per-key sliding window rate limiter.

    Keys typically are user_id / ip / api_key.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._lock = threading.RLock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str = "global") -> bool:
        """Return True if request is allowed (and record it)."""
        now = time.monotonic()
        window = self.config.window_seconds
        with self._lock:
            q = self._hits[key]
            # Drop expired
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= self.config.max_requests:
                return False
            q.append(now)
            return True

    def check(self, key: str = "global") -> None:
        """Raise RateLimitExceeded if over limit."""
        if not self.allow(key):
            raise RateLimitExceeded(
                f"Rate limit exceeded for '{key}' "
                f"({self.config.max_requests}/{self.config.window_seconds}s)"
            )

    def remaining(self, key: str = "global") -> int:
        now = time.monotonic()
        window = self.config.window_seconds
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            return max(0, self.config.max_requests - len(q))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            keys = {}
            for k, q in self._hits.items():
                while q and now - q[0] > self.config.window_seconds:
                    q.popleft()
                keys[k] = {
                    "used": len(q),
                    "remaining": max(0, self.config.max_requests - len(q)),
                }
            return {
                "name": self.config.name,
                "max_requests": self.config.max_requests,
                "window_seconds": self.config.window_seconds,
                "keys": keys,
            }


_limiters: dict[str, RateLimiter] = {}
_lim_lock = threading.Lock()


def get_rate_limiter(
    name: str = "default",
    *,
    max_requests: int = 60,
    window_seconds: float = 60.0,
) -> RateLimiter:
    with _lim_lock:
        if name not in _limiters:
            _limiters[name] = RateLimiter(
                RateLimitConfig(
                    name=name,
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                )
            )
        return _limiters[name]


def reset_rate_limiters() -> None:
    with _lim_lock:
        for lim in _limiters.values():
            lim.reset()
        _limiters.clear()
