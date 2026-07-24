"""In-process performance metrics for production monitoring."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class LatencyStats:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0
    min_seconds: float = float("inf")
    failures: int = 0
    retries: int = 0

    def record(self, seconds: float, *, failed: bool = False, retries: int = 0) -> None:
        self.count += 1
        self.total_seconds += max(0.0, seconds)
        self.max_seconds = max(self.max_seconds, seconds)
        self.min_seconds = min(self.min_seconds, seconds)
        if failed:
            self.failures += 1
        self.retries += max(0, retries)

    @property
    def average_seconds(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_seconds / self.count

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "average_seconds": round(self.average_seconds, 6),
            "max_seconds": round(self.max_seconds if self.count else 0.0, 6),
            "min_seconds": round(self.min_seconds if self.count and self.min_seconds != float("inf") else 0.0, 6),
            "failures": self.failures,
            "retries": self.retries,
        }


class MetricsCollector:
    """
    Collect API / pipeline timing and resource samples.

    Reports:
      average latency, planner/retrieval/acquisition/execution latency,
      memory, CPU, failures, retries
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._latencies: dict[str, LatencyStats] = defaultdict(LatencyStats)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._started_at = time.time()

    def time_block(self, name: str):
        """Context manager to time a named operation."""
        collector = self

        class _Timer:
            def __enter__(self_inner):
                self_inner._t0 = time.perf_counter()
                self_inner._failed = False
                self_inner._retries = 0
                return self_inner

            def mark_failed(self_inner):
                self_inner._failed = True

            def add_retries(self_inner, n: int = 1):
                self_inner._retries += n

            def __exit__(self_inner, exc_type, exc, tb):
                elapsed = time.perf_counter() - self_inner._t0
                failed = self_inner._failed or exc_type is not None
                collector.record_latency(
                    name,
                    elapsed,
                    failed=failed,
                    retries=self_inner._retries,
                )
                return False

        return _Timer()

    def record_latency(
        self,
        name: str,
        seconds: float,
        *,
        failed: bool = False,
        retries: int = 0,
    ) -> None:
        with self._lock:
            self._latencies[name].record(seconds, failed=failed, retries=retries)

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def sample_resources(self) -> dict[str, float]:
        """Sample memory (MB) and CPU percent when possible."""
        mem_mb = 0.0
        cpu = 0.0
        try:
            import os

            import psutil  # type: ignore

            proc = psutil.Process(os.getpid())
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            cpu = proc.cpu_percent(interval=0.0)
        except Exception:
            try:
                import resource

                # ru_maxrss is KB on Linux, bytes on macOS — report best-effort
                mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
            except Exception:
                pass
        with self._lock:
            self._gauges["memory_mb"] = mem_mb
            self._gauges["cpu_percent"] = cpu
        return {"memory_mb": mem_mb, "cpu_percent": cpu}

    def snapshot(self) -> dict[str, Any]:
        self.sample_resources()
        with self._lock:
            lat = {k: v.to_dict() for k, v in self._latencies.items()}
            counters = dict(self._counters)
            gauges = dict(self._gauges)

        def _avg(key: str) -> float:
            return float(lat.get(key, {}).get("average_seconds") or 0.0)

        total_failures = sum(int(v.get("failures") or 0) for v in lat.values())
        total_retries = sum(int(v.get("retries") or 0) for v in lat.values())
        total_retries += int(counters.get("retries") or 0)
        total_failures += int(counters.get("failures") or 0)

        # Overall average across all timed ops
        all_counts = sum(int(v.get("count") or 0) for v in lat.values())
        all_total = sum(
            float(v.get("average_seconds") or 0) * int(v.get("count") or 0) for v in lat.values()
        )
        overall_avg = (all_total / all_counts) if all_counts else 0.0

        return {
            "uptime_seconds": round(time.time() - self._started_at, 3),
            "average_latency": round(overall_avg, 6),
            "planner_latency": _avg("planner"),
            "retrieval_latency": _avg("retrieval"),
            "acquisition_latency": _avg("acquisition"),
            "execution_latency": _avg("execution"),
            "api_latency": _avg("api"),
            "memory_usage_mb": round(float(gauges.get("memory_mb") or 0.0), 3),
            "cpu_usage_percent": round(float(gauges.get("cpu_percent") or 0.0), 3),
            "failures": total_failures,
            "retries": total_retries,
            "latencies": lat,
            "counters": counters,
            "gauges": gauges,
        }

    def reset(self) -> None:
        with self._lock:
            self._latencies.clear()
            self._counters.clear()
            self._gauges.clear()
            self._started_at = time.time()


_default_metrics: MetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    global _default_metrics
    with _metrics_lock:
        if _default_metrics is None:
            _default_metrics = MetricsCollector()
        return _default_metrics


def reset_metrics_collector() -> None:
    global _default_metrics
    with _metrics_lock:
        if _default_metrics is not None:
            _default_metrics.reset()
        _default_metrics = None


def metrics() -> dict[str, Any]:
    """Public metrics snapshot."""
    return get_metrics_collector().snapshot()
