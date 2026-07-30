"""FastAPI middleware that records per-request wall time and stage summaries."""

from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logger import get_logger
from backend.production.metrics import get_metrics_collector
from backend.production.metrics_store import record_metric_sample
from backend.production.pipeline_timing import get_timer

logger = get_logger(__name__)

# Skip noisy paths for SQLite sample volume (still counted in process metrics)
_SKIP_SAMPLE_PREFIXES = (
    "/docs",
    "/openapi",
    "/redoc",
    "/favicon",
)


class PipelineProfilingMiddleware(BaseHTTPMiddleware):
    """
    Records HTTP request duration, memory/CPU sample, and persists metrics.

    When a PipelineTimer is active (set by /ask), labels are merged into that
    timer so a single SQLite sample is written at pipeline_timer exit.
    Safe for all routes; does not alter response bodies.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.perf_counter()
        path = request.url.path
        method = request.method
        response: Response | None = None
        error: str | None = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            status = getattr(response, "status_code", 500 if error else 0)
            success = error is None and int(status or 0) < 500

            # In-process collector
            try:
                collector = get_metrics_collector()
                collector.record_latency(
                    "http",
                    ms / 1000.0,
                    failed=not success,
                )
                collector.incr("http_requests")
                if not success:
                    collector.incr("http_failures")
                resources = collector.sample_resources()
            except Exception:
                resources = {"memory_mb": 0.0, "cpu_percent": 0.0}

            timer = get_timer()
            if timer is not None:
                # Ask path owns the durable sample; annotate timer
                timer.route = path
                timer.status_code = status
                if error:
                    timer.success = False
                    timer.error = error[:500]
                timer.meta.setdefault("http_ms", round(ms, 2))
            else:
                # Non-ask routes: store a lightweight sample
                if not any(path.startswith(p) for p in _SKIP_SAMPLE_PREFIXES):
                    try:
                        record_metric_sample(
                            route=path,
                            method=method,
                            status_code=status,
                            success=success,
                            cache_hit=False,
                            total_ms=ms,
                            memory_mb=resources.get("memory_mb"),
                            cpu_percent=resources.get("cpu_percent"),
                            error=error,
                            stages={"total": round(ms, 3), "response": round(ms, 3)},
                        )
                    except Exception:
                        pass

            logger.info(
                "HTTP request timed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status,
                    "duration_ms": round(ms, 2),
                    "error": error,
                    "memory_mb": resources.get("memory_mb"),
                    "cpu_percent": resources.get("cpu_percent"),
                },
            )
