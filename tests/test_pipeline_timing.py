"""Benchmark / unit tests for pipeline stage timings."""

from __future__ import annotations

import time

from backend.production.pipeline_timing import (
    STAGE_KEYS,
    extract_timings_from_state,
    merge_timings,
    pipeline_timer,
    record_stage_ms,
    reset_aggregate_timing_stats,
    time_stage,
    wrap_agent_with_timing,
    aggregate_timing_stats,
)


def test_time_stage_accumulates_ms():
    reset_aggregate_timing_stats()
    with pipeline_timer(test=True) as timer:
        with time_stage("planner"):
            time.sleep(0.02)
        with time_stage("eda"):
            time.sleep(0.01)
        record_stage_ms("cache", 5.5)
        timings = timer.as_dict()

    assert timings["planner"] >= 15
    assert timings["eda"] >= 5
    assert timings["cache"] == 6 or timings["cache"] == 5
    assert "total" in timings
    assert timings["total"] >= timings["planner"]

    agg = aggregate_timing_stats()
    assert "planner" in agg
    assert agg["planner"]["count"] >= 1


def test_wrap_agent_records_stage_on_state():
    reset_aggregate_timing_stats()

    def fake_eda(state):
        time.sleep(0.01)
        return {**state, "answer": "ok"}

    timed = wrap_agent_with_timing("run_eda", fake_eda)
    with pipeline_timer():
        out = timed({"plan": ["run_eda"]})

    assert out["answer"] == "ok"
    assert out["timings"]["eda"] >= 5
    assert "stage_timings" in out


def test_merge_and_extract_timings():
    a = {"planner": 10, "eda": 20}
    b = {"eda": 5, "forecast": 30}
    m = merge_timings(a, b)
    assert m["planner"] == 10
    assert m["eda"] == 25
    assert m["forecast"] == 30

    state = {"timings": {"retrieval": 100.4}}
    assert extract_timings_from_state(state)["retrieval"] == 100


def test_stable_response_includes_timings():
    from backend.main import _stable_response
    from backend.production.pipeline_timing import pipeline_timer

    with pipeline_timer():
        record_stage_ms("planner", 42)
        record_stage_ms("retrieval", 310)
        record_stage_ms("eda", 620)
        payload = _stable_response(
            {
                "answer": "hi",
                "stage_timings": {"forecast": 970, "download": 840},
            },
            question="test",
        )

    assert "timings" in payload
    t = payload["timings"]
    assert t["planner"] == 42
    assert t["retrieval"] == 310
    assert t["eda"] == 620
    assert t["forecast"] == 970
    assert t["download"] == 840
    assert "total" in t


def test_benchmark_cold_path_records_multiple_stages():
    """Lightweight synthetic pipeline benchmark (no Ollama)."""
    reset_aggregate_timing_stats()

    def planner(state):
        time.sleep(0.005)
        return {**state, "plan": ["run_eda", "run_viz", "forecast_data", "generate_insight"]}

    def eda(state):
        time.sleep(0.008)
        return state

    def viz(state):
        time.sleep(0.006)
        return state

    def forecast(state):
        time.sleep(0.007)
        return state

    def insight(state):
        time.sleep(0.004)
        return {**state, "answer": "done"}

    with pipeline_timer(bench=True) as timer:
        with time_stage("intent"):
            time.sleep(0.002)
        with time_stage("session"):
            time.sleep(0.002)
        with time_stage("cache"):
            time.sleep(0.001)  # miss path
        state = {}
        for name, fn in [
            ("planner", planner),
            ("run_eda", eda),
            ("run_viz", viz),
            ("forecast_data", forecast),
            ("generate_insight", insight),
        ]:
            state = wrap_agent_with_timing(name, fn)(state)

        timings = timer.as_dict()

    for key in ("intent", "session", "cache", "planner", "eda", "visualization", "forecast", "insights", "total"):
        assert key in timings, f"missing {key}"
        assert timings[key] >= 0

    # total roughly covers sum of stages (allow overhead variance)
    assert timings["total"] >= 10
