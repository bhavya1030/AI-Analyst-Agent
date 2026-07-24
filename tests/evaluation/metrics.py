"""Evaluation metrics aggregation for the analytics copilot suite."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class EvaluationMetrics:
    """Suite-level metrics summary."""

    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0

    average_response_time: float = 0.0
    average_retrieval_time: float = 0.0
    average_acquisition_time: float = 0.0
    average_analysis_time: float = 0.0
    average_confidence: float = 0.0

    # Capability scores (0–1 means)
    dataset_retrieval_accuracy: float = 0.0
    dataset_selection_accuracy: float = 0.0
    semantic_search_accuracy: float = 0.0
    planner_accuracy: float = 0.0
    context_resolution_accuracy: float = 0.0
    join_accuracy: float = 0.0
    forecast_execution: float = 0.0
    chart_generation: float = 0.0
    explanation_quality: float = 0.0
    failure_recovery: float = 0.0
    success_rate: float = 0.0

    # Resource / latency extras
    p95_response_time: float = 0.0
    max_response_time: float = 0.0
    average_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0

    failure_reasons: list[dict[str, Any]] = field(default_factory=list)
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return round(ordered[idx], 4)


def _dim_mean(records: list[dict[str, Any]], key: str) -> float:
    vals: list[float] = []
    for r in records:
        scores = r.get("scores") or {}
        v = scores.get(key)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return _mean(vals)


def aggregate_metrics(records: list[dict[str, Any]]) -> EvaluationMetrics:
    """Aggregate per-case evaluation records into suite metrics."""
    m = EvaluationMetrics()
    m.total_tests = len(records)
    if not records:
        return m

    response_times: list[float] = []
    retrieval_times: list[float] = []
    acquisition_times: list[float] = []
    analysis_times: list[float] = []
    confidences: list[float] = []
    memory_vals: list[float] = []

    cat_stats: dict[str, dict[str, int]] = {}

    for r in records:
        status = str(r.get("status") or "failed")
        if status == "passed":
            m.passed += 1
        elif status == "warning":
            m.warnings += 1
        elif status == "skipped":
            m.skipped += 1
        else:
            m.failed += 1

        cat = str(r.get("category") or "unknown")
        cat_stats.setdefault(cat, {"total": 0, "passed": 0, "failed": 0, "warnings": 0})
        cat_stats[cat]["total"] += 1
        if status == "passed":
            cat_stats[cat]["passed"] += 1
        elif status == "warning":
            cat_stats[cat]["warnings"] += 1
        elif status != "skipped":
            cat_stats[cat]["failed"] += 1

        for key, bucket in (
            ("execution_time", response_times),
            ("retrieval_time", retrieval_times),
            ("acquisition_time", acquisition_times),
            ("analysis_time", analysis_times),
        ):
            try:
                if r.get(key) is not None:
                    bucket.append(float(r[key]))
            except (TypeError, ValueError):
                pass

        try:
            if r.get("confidence") is not None:
                confidences.append(float(r["confidence"]))
        except (TypeError, ValueError):
            pass

        try:
            if r.get("memory_mb") is not None:
                memory_vals.append(float(r["memory_mb"]))
        except (TypeError, ValueError):
            pass

        if status == "failed":
            reason = {
                "id": r.get("id"),
                "question": (r.get("question") or "")[:120],
                "category": cat,
                "errors": list(r.get("errors") or [])[:5],
                "crashed": bool(r.get("crashed")),
                "mean_score": (r.get("scores") or {}).get("mean"),
            }
            m.failure_reasons.append(reason)

    m.average_response_time = _mean(response_times)
    m.average_retrieval_time = _mean(retrieval_times)
    m.average_acquisition_time = _mean(acquisition_times)
    m.average_analysis_time = _mean(analysis_times)
    m.average_confidence = _mean(confidences)
    m.p95_response_time = _p95(response_times)
    m.max_response_time = round(max(response_times), 4) if response_times else 0.0
    m.average_memory_mb = _mean(memory_vals)
    m.peak_memory_mb = round(max(memory_vals), 4) if memory_vals else 0.0

    m.dataset_retrieval_accuracy = _dim_mean(records, "retrieval")
    m.dataset_selection_accuracy = _dim_mean(records, "selection")
    m.semantic_search_accuracy = _dim_mean(records, "semantic")
    m.planner_accuracy = _dim_mean(records, "planner")
    m.context_resolution_accuracy = _dim_mean(records, "context")
    m.join_accuracy = _dim_mean(records, "join")
    m.forecast_execution = _dim_mean(records, "forecast")
    m.chart_generation = _dim_mean(records, "chart")
    m.explanation_quality = _dim_mean(records, "explanation")
    m.failure_recovery = _dim_mean(records, "failure_recovery")

    denom = m.total_tests - m.skipped
    m.success_rate = round(m.passed / denom, 4) if denom else 0.0

    for cat, stats in cat_stats.items():
        total = stats["total"] or 1
        m.by_category[cat] = {
            **stats,
            "pass_rate": round(stats["passed"] / total, 4),
        }

    return m
