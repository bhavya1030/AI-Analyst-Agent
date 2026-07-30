"""Performance monitoring — metrics collection, dashboard, API, concurrency."""

from __future__ import annotations

import concurrent.futures
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.production.metrics import get_metrics_collector, reset_metrics_collector
from backend.production.metrics_store import (
    clear_metric_samples,
    list_metric_samples,
    record_metric_sample,
)
from backend.production.observability_router import router as obs_router
from backend.production.performance import (
    build_performance_dashboard,
    latency_summary,
    to_prometheus,
)
from backend.production.pipeline_timing import (
    pipeline_timer,
    record_stage_ms,
    reset_aggregate_timing_stats,
    time_stage,
    aggregate_timing_stats,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_metrics_collector()
    reset_aggregate_timing_stats()
    clear_metric_samples()
    yield
    reset_metrics_collector()
    reset_aggregate_timing_stats()
    clear_metric_samples()


# ── unit: collection ───────────────────────────────────────────────────────


def test_pipeline_stages_recorded_and_persisted():
    with pipeline_timer(session_id="obs-1", question="gdp", route="/v1/ask") as timer:
        with time_stage("planner"):
            time.sleep(0.01)
        with time_stage("retrieval"):
            time.sleep(0.01)
        with time_stage("validation"):
            time.sleep(0.005)
        with time_stage("download"):
            time.sleep(0.005)
        with time_stage("eda"):
            time.sleep(0.005)
        with time_stage("visualization"):
            time.sleep(0.005)
        with time_stage("forecast"):
            time.sleep(0.005)
        with time_stage("insights"):
            time.sleep(0.005)
        with time_stage("cache"):
            time.sleep(0.002)
        with time_stage("serialization"):
            time.sleep(0.002)
        with time_stage("response"):
            time.sleep(0.002)
        timer.record_provider_latency("world_bank", 12.5)
        timer.forecast_model = "holt_winters"
        timer.chart_type = "line"
        timer.cache_hit = False
        timer.success = True
        timings = timer.as_dict()

    assert timings["planner"] >= 5
    assert timings["retrieval"] >= 5
    assert timings["total"] >= timings["planner"]
    assert "provider" in timings

    samples = list_metric_samples(limit=10)
    assert len(samples) >= 1
    sample = samples[0]
    assert sample["forecast_model"] == "holt_winters"
    assert sample["chart_type"] == "line"
    assert sample["stages"].get("planner") is not None
    assert sample["total_ms"] > 0

    agg = aggregate_timing_stats()
    assert agg["planner"]["count"] >= 1
    assert "p50_ms" in agg["planner"]
    assert "p95_ms" in agg["planner"]


def test_latency_summary_percentiles():
    vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    s = latency_summary(vals)
    assert s["count"] == 10
    assert s["min"] == 10
    assert s["max"] == 100
    assert 40 <= s["p50"] <= 60
    assert s["p95"] >= s["p50"]
    assert s["average"] == 55.0


def test_cache_hit_and_failure_metrics():
    with pipeline_timer(session_id="hit") as t:
        record_stage_ms("cache", 3)
        t.cache_hit = True
        t.success = True
    with pipeline_timer(session_id="fail") as t2:
        record_stage_ms("planner", 5)
        t2.success = False
        t2.error = "boom"

    samples = list_metric_samples(limit=20)
    assert any(s.get("cache_hit") for s in samples)
    assert any(not s.get("success") for s in samples)

    live = get_metrics_collector().snapshot()
    assert live["counters"].get("cache_hits", 0) >= 1
    assert live["failures"] >= 1 or live["counters"].get("failures", 0) >= 1


# ── dashboard ──────────────────────────────────────────────────────────────


def test_dashboard_json_shape():
    for i in range(15):
        record_metric_sample(
            route="/v1/ask",
            method="GET",
            status_code=200 if i < 13 else 500,
            success=i < 13,
            cache_hit=(i % 3 == 0),
            total_ms=50 + i * 10,
            memory_mb=100 + i,
            cpu_percent=5 + i * 0.1,
            forecast_model="linear" if i % 2 == 0 else "holt_winters",
            chart_type="line" if i % 2 == 0 else "bar",
            provider="world_bank",
            stages={
                "planner": 10 + i,
                "retrieval": 20 + i,
                "forecast": 30 + i,
                "provider": 15 + i,
                "total": 50 + i * 10,
            },
        )

    dash = build_performance_dashboard(limit=50)
    assert "summary" in dash
    assert "stages" in dash
    assert dash["summary"]["requests"] >= 15
    assert 0 <= dash["error_rate"] <= 1
    assert 0 <= dash["cache_hit_ratio"] <= 1
    assert dash["p95"] >= dash["p50"]
    assert dash["average"] > 0
    assert dash["max"] >= dash["min"]
    assert "planner" in dash["stages"]
    assert dash["planner_latency"]["count"] >= 1
    assert dash["forecast_latency"]["count"] >= 1
    assert dash["provider_latency"]["count"] >= 1
    assert "forecast_models" in dash["distributions"]


def test_prometheus_format():
    record_metric_sample(
        route="/v1/ask",
        total_ms=120,
        success=True,
        cache_hit=True,
        stages={"planner": 20, "total": 120},
    )
    text = to_prometheus()
    assert "ai_analyst_requests_total" in text
    assert "ai_analyst_error_rate" in text
    assert "ai_analyst_cache_hit_ratio" in text
    assert "ai_analyst_latency_ms" in text
    assert "quantile" in text


# ── concurrent collection ──────────────────────────────────────────────────


def test_concurrent_metric_recording():
    def worker(i: int):
        with pipeline_timer(session_id=f"c-{i}") as timer:
            with time_stage("planner"):
                time.sleep(0.002)
            with time_stage("eda"):
                time.sleep(0.002)
            timer.chart_type = "histogram"
            timer.success = True
        return i

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(worker, i) for i in range(40)]
        results = [f.result() for f in concurrent.futures.as_completed(futs)]
    assert len(results) == 40

    samples = list_metric_samples(limit=100)
    assert len(samples) >= 40
    dash = build_performance_dashboard(limit=100)
    assert dash["summary"]["requests"] >= 40
    assert dash["p95"] >= 0


# ── API endpoints ──────────────────────────────────────────────────────────


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(obs_router)
    return TestClient(app)


def test_api_health():
    c = _client()
    r = c.get("/health")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "status" in body
    assert body["status"] in {"healthy", "degraded", "unhealthy"}
    assert "components" in body


def test_api_metrics_json_and_prometheus():
    # seed
    with pipeline_timer(session_id="api-m") as t:
        record_stage_ms("planner", 12)
        record_stage_ms("retrieval", 40)
        t.success = True

    c = _client()
    r = c.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "live" in body
    assert "stages" in body
    assert "store" in body

    r2 = c.get("/metrics?format=prometheus")
    assert r2.status_code == 200
    assert "ai_analyst_requests_total" in r2.text
    assert r2.headers["content-type"].startswith("text/plain")

    r3 = c.get("/metrics/prometheus")
    assert r3.status_code == 200
    assert "ai_analyst_" in r3.text


def test_api_performance_dashboard():
    for i in range(8):
        record_metric_sample(
            route="/v1/ask",
            total_ms=80 + i * 5,
            success=True,
            cache_hit=i % 2 == 0,
            stages={"planner": 10, "forecast": 25, "total": 80 + i * 5},
            forecast_model="linear",
            chart_type="scatter",
        )
    c = _client()
    r = c.get("/performance")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "p50",
        "p95",
        "average",
        "max",
        "min",
        "error_rate",
        "cache_hit_ratio",
        "forecast_latency",
        "provider_latency",
        "planner_latency",
        "stages",
        "summary",
    ):
        assert key in body, f"missing {key}"


def test_v1_aliases():
    c = _client()
    assert c.get("/v1/health").status_code in (200, 503)
    assert c.get("/v1/metrics").status_code == 200
    assert c.get("/v1/performance").status_code == 200
