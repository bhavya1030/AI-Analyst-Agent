"""Performance dashboard aggregation — P50/P95, rates, stage latencies."""

from __future__ import annotations

import statistics
import time
from typing import Any, Iterable, Optional, Sequence

from backend.production.metrics import get_metrics_collector
from backend.production.metrics_store import list_metric_samples, metrics_store_stats
from backend.production.pipeline_timing import STAGE_KEYS, aggregate_timing_stats

# Stages required by the product brief
DASHBOARD_STAGES = (
    "planner",
    "retrieval",
    "validation",
    "download",
    "eda",
    "visualization",
    "forecast",
    "insights",
    "cache",
    "serialization",
    "response",
    "provider",
    "total",
)


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    # Nearest-rank
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return float(d0 + d1)


def latency_summary(values: Iterable[float]) -> dict[str, float]:
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return {
            "count": 0,
            "p50": 0.0,
            "p95": 0.0,
            "average": 0.0,
            "max": 0.0,
            "min": 0.0,
        }
    return {
        "count": len(vals),
        "p50": round(_percentile(vals, 50), 3),
        "p95": round(_percentile(vals, 95), 3),
        "average": round(sum(vals) / len(vals), 3),
        "max": round(max(vals), 3),
        "min": round(min(vals), 3),
    }


def build_performance_dashboard(
    *,
    limit: int = 500,
    since_minutes: float | None = None,
) -> dict[str, Any]:
    """
    Dashboard JSON for GET /performance.

    Includes P50/P95/avg/min/max, error rate, cache hit ratio,
    forecast / provider / planner latencies, resource gauges.
    """
    since_ts = None
    if since_minutes is not None and since_minutes > 0:
        since_ts = time.time() - (float(since_minutes) * 60.0)

    samples = list_metric_samples(limit=limit, since_ts=since_ts)
    n = len(samples)
    successes = sum(1 for s in samples if s.get("success"))
    failures = n - successes
    cache_hits = sum(1 for s in samples if s.get("cache_hit"))
    asks = [s for s in samples if (s.get("route") or "").endswith("/ask") or "ask" in (s.get("route") or "")]
    cache_eligible = asks or samples
    cache_hit_ratio = (
        (sum(1 for s in cache_eligible if s.get("cache_hit")) / len(cache_eligible))
        if cache_eligible
        else 0.0
    )

    total_lat = [float(s.get("total_ms") or 0) for s in samples]
    overall = latency_summary(total_lat)

    # Per-stage from sample stages blobs
    stage_values: dict[str, list[float]] = {k: [] for k in DASHBOARD_STAGES}
    provider_values: list[float] = []
    forecast_values: list[float] = []
    planner_values: list[float] = []
    forecast_models: dict[str, int] = {}
    chart_types: dict[str, int] = {}
    providers: dict[str, int] = {}

    for s in samples:
        stages = s.get("stages") or {}
        if not isinstance(stages, dict):
            stages = {}
        for key in DASHBOARD_STAGES:
            if key in stages and stages[key] is not None:
                try:
                    stage_values[key].append(float(stages[key]))
                except Exception:
                    pass
        # aliases
        for alias, target in (
            ("provider_latency_ms", "provider"),
            ("provider_ms", "provider"),
        ):
            if alias in stages:
                try:
                    stage_values["provider"].append(float(stages[alias]))
                except Exception:
                    pass
        if "planner" in stages:
            try:
                planner_values.append(float(stages["planner"]))
            except Exception:
                pass
        if "forecast" in stages:
            try:
                forecast_values.append(float(stages["forecast"]))
            except Exception:
                pass
        if "provider" in stages:
            try:
                provider_values.append(float(stages["provider"]))
            except Exception:
                pass
        # Also average provider latencies nested dict
        prov_map = stages.get("provider_latency_ms")
        if isinstance(prov_map, dict):
            for v in prov_map.values():
                try:
                    provider_values.append(float(v))
                    stage_values["provider"].append(float(v))
                except Exception:
                    pass

        fm = s.get("forecast_model")
        if fm:
            forecast_models[str(fm)] = forecast_models.get(str(fm), 0) + 1
        ct = s.get("chart_type")
        if ct:
            chart_types[str(ct)] = chart_types.get(str(ct), 0) + 1
        pr = s.get("provider")
        if pr:
            providers[str(pr)] = providers.get(str(pr), 0) + 1

    stages_summary = {
        k: latency_summary(stage_values.get(k) or []) for k in DASHBOARD_STAGES
    }

    # Resource averages from samples
    mems = [float(s["memory_mb"]) for s in samples if s.get("memory_mb") is not None]
    cpus = [float(s["cpu_percent"]) for s in samples if s.get("cpu_percent") is not None]

    live = get_metrics_collector().snapshot()
    inproc_stages = aggregate_timing_stats()

    error_rate = (failures / n) if n else 0.0

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {
            "samples": n,
            "since_minutes": since_minutes,
            "limit": limit,
        },
        "summary": {
            "requests": n,
            "successes": successes,
            "failures": failures,
            "error_rate": round(error_rate, 4),
            "cache_hits": cache_hits,
            "cache_hit_ratio": round(cache_hit_ratio, 4),
            "latency_ms": overall,
            "planner_latency_ms": latency_summary(planner_values),
            "forecast_latency_ms": latency_summary(forecast_values),
            "provider_latency_ms": latency_summary(provider_values),
            "memory_mb": {
                "average": round(sum(mems) / len(mems), 3) if mems else live.get("memory_usage_mb", 0),
                "max": round(max(mems), 3) if mems else 0.0,
                "min": round(min(mems), 3) if mems else 0.0,
            },
            "cpu_percent": {
                "average": round(sum(cpus) / len(cpus), 3) if cpus else live.get("cpu_usage_percent", 0),
                "max": round(max(cpus), 3) if cpus else 0.0,
            },
        },
        "stages": stages_summary,
        "distributions": {
            "forecast_models": forecast_models,
            "chart_types": chart_types,
            "providers": providers,
        },
        "in_process": {
            "metrics": live,
            "stage_aggregates": inproc_stages,
            "store": metrics_store_stats(),
        },
        # Convenience top-level mirrors for the brief
        "p50": overall["p50"],
        "p95": overall["p95"],
        "average": overall["average"],
        "max": overall["max"],
        "min": overall["min"],
        "error_rate": round(error_rate, 4),
        "cache_hit_ratio": round(cache_hit_ratio, 4),
        "forecast_latency": stages_summary.get("forecast") or latency_summary(forecast_values),
        "provider_latency": stages_summary.get("provider") or latency_summary(provider_values),
        "planner_latency": stages_summary.get("planner") or latency_summary(planner_values),
    }


def to_prometheus(dashboard: dict[str, Any] | None = None) -> str:
    """Render a Prometheus text exposition of key gauges."""
    dash = dashboard or build_performance_dashboard(limit=500)
    summary = dash.get("summary") or {}
    lat = summary.get("latency_ms") or {}
    lines: list[str] = [
        "# HELP ai_analyst_requests_total Total observed requests in window",
        "# TYPE ai_analyst_requests_total gauge",
        f"ai_analyst_requests_total {int(summary.get('requests') or 0)}",
        "# HELP ai_analyst_error_rate Request error rate (0-1)",
        "# TYPE ai_analyst_error_rate gauge",
        f"ai_analyst_error_rate {float(summary.get('error_rate') or 0)}",
        "# HELP ai_analyst_cache_hit_ratio Cache hit ratio (0-1)",
        "# TYPE ai_analyst_cache_hit_ratio gauge",
        f"ai_analyst_cache_hit_ratio {float(summary.get('cache_hit_ratio') or 0)}",
        "# HELP ai_analyst_latency_ms Request latency milliseconds",
        "# TYPE ai_analyst_latency_ms summary",
        f'ai_analyst_latency_ms{{quantile="0.5"}} {float(lat.get("p50") or 0)}',
        f'ai_analyst_latency_ms{{quantile="0.95"}} {float(lat.get("p95") or 0)}',
        f"ai_analyst_latency_ms_sum {float(lat.get('average') or 0) * float(lat.get('count') or 0)}",
        f"ai_analyst_latency_ms_count {int(lat.get('count') or 0)}",
    ]
    stages = dash.get("stages") or {}
    for stage, stats in stages.items():
        if not isinstance(stats, dict) or not stats.get("count"):
            continue
        safe = str(stage).replace('"', "")
        lines.append(
            f'ai_analyst_stage_latency_ms{{stage="{safe}",stat="p50"}} {float(stats.get("p50") or 0)}'
        )
        lines.append(
            f'ai_analyst_stage_latency_ms{{stage="{safe}",stat="p95"}} {float(stats.get("p95") or 0)}'
        )
        lines.append(
            f'ai_analyst_stage_latency_ms{{stage="{safe}",stat="average"}} {float(stats.get("average") or 0)}'
        )
    mem = (summary.get("memory_mb") or {}).get("average") or 0
    cpu = (summary.get("cpu_percent") or {}).get("average") or 0
    lines.append("# HELP ai_analyst_memory_mb Process memory megabytes")
    lines.append("# TYPE ai_analyst_memory_mb gauge")
    lines.append(f"ai_analyst_memory_mb {float(mem)}")
    lines.append("# HELP ai_analyst_cpu_percent Process CPU percent")
    lines.append("# TYPE ai_analyst_cpu_percent gauge")
    lines.append(f"ai_analyst_cpu_percent {float(cpu)}")
    lines.append("")
    return "\n".join(lines)
