"""HTTP routes for metrics, health, and performance dashboard."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.core.logger import get_logger
from backend.production.health import health as build_health
from backend.production.metrics import get_metrics_collector, metrics as metrics_snapshot
from backend.production.metrics_store import list_metric_samples, metrics_store_stats
from backend.production.performance import build_performance_dashboard, to_prometheus
from backend.production.pipeline_timing import aggregate_timing_stats
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

router = APIRouter(tags=["observability"])


@router.get("/health")
@router.get("/v1/health")
def health_endpoint(deep: bool = Query(False, description="Include config validation")):
    """Liveness / readiness style health with component breakdown."""
    try:
        report = build_health(deep=deep)
        # Enrich with metrics store + process gauges
        try:
            resources = get_metrics_collector().sample_resources()
            report["resources"] = resources
            report["metrics_store"] = metrics_store_stats()
        except Exception:
            pass
        code = 200 if report.get("status") in {"healthy", "degraded"} else 503
        return JSONResponse(status_code=code, content=sanitize_for_json(report))
    except Exception as exc:
        logger.error("Health check failed", extra={"error": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(exc)},
        )


@router.get("/metrics")
@router.get("/v1/metrics")
def metrics_endpoint(
    request: Request,
    format: Optional[str] = Query(
        None,
        description="json (default) | prometheus",
    ),
    limit: int = Query(200, ge=1, le=2000),
):
    """
    Metrics snapshot.

    - JSON: in-process counters/latencies + recent SQLite samples + stage aggregates
    - Prometheus: text exposition (`?format=prometheus` or Accept: text/plain)
    """
    accept = (request.headers.get("accept") or "").lower()
    want_prom = (format or "").lower() in {"prometheus", "prom", "text"} or (
        "text/plain" in accept and "application/json" not in accept
    )
    if want_prom:
        body = to_prometheus(build_performance_dashboard(limit=limit))
        return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")

    live = metrics_snapshot()
    stages = aggregate_timing_stats()
    samples = list_metric_samples(limit=min(limit, 100))
    store = metrics_store_stats()
    return sanitize_for_json(
        {
            "live": live,
            "stages": stages,
            "store": store,
            "recent_samples": samples,
            "prometheus_hint": "Add ?format=prometheus for text exposition",
        }
    )


@router.get("/performance")
@router.get("/v1/performance")
def performance_endpoint(
    limit: int = Query(500, ge=1, le=5000),
    since_minutes: Optional[float] = Query(
        None, description="Only include samples from the last N minutes"
    ),
):
    """Dashboard JSON: P50/P95/avg/min/max, error rate, cache hit ratio, stage latencies."""
    dash = build_performance_dashboard(limit=limit, since_minutes=since_minutes)
    return sanitize_for_json(dash)


@router.get("/metrics/prometheus")
@router.get("/v1/metrics/prometheus")
def metrics_prometheus(limit: int = Query(500, ge=1, le=5000)):
    """Explicit Prometheus scrape endpoint."""
    body = to_prometheus(build_performance_dashboard(limit=limit))
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")
