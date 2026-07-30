"""Pipeline stage timing for /v1/ask and LangGraph nodes.

Uses contextvars so timings accumulate across graph nodes without changing
agent signatures. Millisecond integers are returned in API responses as:

    {
      "timings": {
        "planner": 42,
        "retrieval": 310,
        "total": 2840,
        ...
      }
    }
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Generator, Iterator, Optional

from backend.core.logger import get_logger

logger = get_logger(__name__)

# Canonical stage keys exposed in API responses
STAGE_KEYS = (
    "planner",
    "intent",
    "retrieval",
    "download",
    "validation",
    "profiling",
    "eda",
    "visualization",
    "forecast",
    "insights",
    "session",
    "cache",
    "total",
)

# Map LangGraph node names → public stage keys (summed if multiple nodes map)
NODE_TO_STAGE: dict[str, str] = {
    "conversation_context": "intent",
    "planner": "planner",
    "retrieve_dataset": "retrieval",
    "dataset_search_agent": "retrieval",
    "dataset_embedding_search": "retrieval",
    "dataset_topic_agent": "retrieval",
    "dataset_topic_detection": "retrieval",
    # prepare_dataset records download/validation/profiling internally
    "load_data": "download",
    "fetch_data": "download",
    "profile_data": "profiling",
    "pattern_detection": "eda",
    "run_eda": "eda",
    "run_viz": "visualization",
    "run_multi_viz": "visualization",
    "chart_interpretation": "visualization",
    "forecast_data": "forecast",
    "generate_insight": "insights",
    "hypothesis_generation": "insights",
    "recommend_analysis": "insights",
    "explain_dataset": "insights",
    "run_qa": "insights",
    "compare_datasets": "eda",
    "clean_data": "profiling",
}

_current: ContextVar[Optional["PipelineTimer"]] = ContextVar(
    "pipeline_timer", default=None
)

# Aggregate process metrics (for /metrics-style reports)
_AGG_LOCK = threading.RLock()
_AGG: dict[str, dict[str, float]] = {
    # stage -> {count, total_ms, max_ms}
}


@dataclass
class PipelineTimer:
    """Accumulates stage durations (milliseconds) for one request."""

    stages: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)
    meta: dict[str, Any] = field(default_factory=dict)

    def add_ms(self, stage: str, ms: float) -> None:
        if not stage or ms < 0:
            return
        key = str(stage)
        self.stages[key] = float(self.stages.get(key, 0.0)) + float(ms)
        self.counts[key] = int(self.counts.get(key, 0)) + 1

    def add_seconds(self, stage: str, seconds: float) -> None:
        self.add_ms(stage, seconds * 1000.0)

    def mark_total(self) -> None:
        elapsed = (time.perf_counter() - self.started_at) * 1000.0
        self.stages["total"] = round(elapsed, 2)

    def as_dict(self) -> dict[str, int]:
        """Integer ms per stage (API contract). Always includes known keys when present."""
        self.mark_total()
        out: dict[str, int] = {}
        # Prefer stable order of known stages, then any extras
        ordered = list(STAGE_KEYS) + [
            k for k in self.stages.keys() if k not in STAGE_KEYS
        ]
        for key in ordered:
            if key in self.stages:
                out[key] = int(round(self.stages[key]))
        # Ensure total always present
        if "total" not in out:
            out["total"] = int(round((time.perf_counter() - self.started_at) * 1000))
        return out

    def merge_into_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state = state if isinstance(state, dict) else {}
        existing = state.get("stage_timings") or state.get("timings") or {}
        if not isinstance(existing, dict):
            existing = {}
        merged = dict(existing)
        for k, v in self.stages.items():
            merged[k] = float(merged.get(k, 0.0)) + float(v)
        state["stage_timings"] = merged
        state["timings"] = {k: int(round(v)) for k, v in merged.items()}
        return state


def get_timer() -> Optional[PipelineTimer]:
    return _current.get()


def start_timer(**meta: Any) -> tuple[PipelineTimer, Token]:
    timer = PipelineTimer(meta=dict(meta or {}))
    token = _current.set(timer)
    return timer, token


def reset_timer(token: Token | None) -> None:
    if token is not None:
        try:
            _current.reset(token)
        except Exception:
            _current.set(None)


@contextmanager
def pipeline_timer(**meta: Any) -> Generator[PipelineTimer, None, None]:
    timer, token = start_timer(**meta)
    try:
        yield timer
    finally:
        timer.mark_total()
        _publish_aggregate(timer)
        reset_timer(token)


@contextmanager
def time_stage(stage: str) -> Iterator[None]:
    """Time a named stage into the current request timer (no-op if none)."""
    timer = get_timer()
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        if timer is not None:
            timer.add_ms(stage, ms)
        logger.info(
            "Stage timing",
            extra={
                "stage": stage,
                "duration_ms": round(ms, 2),
                "has_timer": timer is not None,
            },
        )


def record_stage_ms(stage: str, ms: float) -> None:
    timer = get_timer()
    if timer is not None:
        timer.add_ms(stage, ms)
    logger.info(
        "Stage timing",
        extra={"stage": stage, "duration_ms": round(ms, 2), "has_timer": timer is not None},
    )


def time_callable(stage: str, fn, *args, **kwargs):
    with time_stage(stage):
        return fn(*args, **kwargs)


def wrap_agent_with_timing(node_name: str, agent):
    """Wrap a LangGraph agent to record stage duration on state."""

    stage = NODE_TO_STAGE.get(node_name)  # None = time node name privately only

    def _timed(state):
        t0 = time.perf_counter()
        try:
            result = agent(state)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000.0
            if stage:
                record_stage_ms(stage, ms)
            raise
        ms = (time.perf_counter() - t0) * 1000.0
        if stage:
            record_stage_ms(stage, ms)
        if isinstance(result, dict):
            timings = dict(result.get("stage_timings") or {})
            if stage:
                timings[stage] = float(timings.get(stage, 0.0)) + ms
            # Map prepare_dataset sub-hints if agent set them
            for sub in ("download", "validation", "profiling"):
                if result.get(f"_{sub}_ms") is not None:
                    timings[sub] = float(timings.get(sub, 0.0)) + float(
                        result.get(f"_{sub}_ms") or 0
                    )
                    # Also ensure context timer sees sub-stage if agent only set state
                    timer = get_timer()
                    if timer is not None and result.get(f"_{sub}_ms") is not None:
                        # Avoid double-count when prepare already used time_stage
                        pass
            result["stage_timings"] = timings
            result["timings"] = {k: int(round(v)) for k, v in timings.items()}
            logger.info(
                "Graph node timed",
                extra={
                    "node": node_name,
                    "stage": stage or node_name,
                    "duration_ms": round(ms, 2),
                },
            )
            return result
        return result

    return _timed


def extract_timings_from_state(state: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(state, dict):
        return {}
    raw = state.get("timings") or state.get("stage_timings") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(round(float(v)))
        except Exception:
            continue
    return out


def merge_timings(*parts: dict[str, Any] | None) -> dict[str, int]:
    acc: dict[str, float] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for k, v in part.items():
            try:
                acc[str(k)] = float(acc.get(str(k), 0.0)) + float(v)
            except Exception:
                continue
    if "total" not in acc and acc:
        # leave total to caller
        pass
    return {k: int(round(v)) for k, v in acc.items()}


def _publish_aggregate(timer: PipelineTimer) -> None:
    with _AGG_LOCK:
        for stage, ms in timer.stages.items():
            slot = _AGG.setdefault(stage, {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0})
            slot["count"] += 1
            slot["total_ms"] += ms
            slot["max_ms"] = max(slot["max_ms"], ms)


def aggregate_timing_stats() -> dict[str, Any]:
    with _AGG_LOCK:
        out: dict[str, Any] = {}
        for stage, slot in _AGG.items():
            count = int(slot["count"])
            total = float(slot["total_ms"])
            out[stage] = {
                "count": count,
                "avg_ms": round(total / count, 2) if count else 0.0,
                "max_ms": round(float(slot["max_ms"]), 2),
                "total_ms": round(total, 2),
            }
        return out


def reset_aggregate_timing_stats() -> None:
    with _AGG_LOCK:
        _AGG.clear()
