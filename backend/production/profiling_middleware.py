"""FastAPI middleware that records per-request wall time and stage summaries."""

from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logger import get_logger
from backend.production.pipeline_timing import get_timer, record_stage_ms

logger = get_logger(__name__)


class PipelineProfilingMiddleware(BaseHTTPMiddleware):
    """
    Records HTTP request duration. When a PipelineTimer is active (set by /ask),
    the middleware contributes no stages itself beyond logging wall time.

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
            logger.info(
                "HTTP request timed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status,
                    "duration_ms": round(ms, 2),
                    "error": error,
                },
            )
