"""Tests for Production Readiness framework (Task 25)."""

from __future__ import annotations

import time

import pytest

from backend.production import (
    CircuitOpenError,
    RateLimitExceeded,
    RetryPolicy,
    configure_structured_logging,
    get_circuit_breaker,
    get_metrics_collector,
    get_rate_limiter,
    get_request_id,
    get_request_tracker,
    get_tracer,
    health,
    metrics,
    new_request_id,
    reset_circuit_breakers,
    reset_metrics_collector,
    reset_rate_limiters,
    reset_request_tracker,
    reset_tracer,
    retry_call,
    set_request_id,
    trace_request,
    validate_config,
)
from backend.production.logging import clear_context


@pytest.fixture(autouse=True)
def _reset():
    reset_metrics_collector()
    reset_tracer()
    reset_request_tracker()
    reset_circuit_breakers()
    reset_rate_limiters()
    clear_context()
    yield
    reset_metrics_collector()
    reset_tracer()
    reset_request_tracker()
    reset_circuit_breakers()
    reset_rate_limiters()
    clear_context()


# ---------------------------------------------------------------------------
# Logging / request IDs
# ---------------------------------------------------------------------------


def test_request_id_context():
    rid = new_request_id()
    set_request_id(rid)
    assert get_request_id() == rid
    clear_context()
    assert get_request_id() == ""


def test_configure_structured_logging():
    logger = configure_structured_logging(level="INFO", force=True)
    assert logger is not None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_latency_and_resources():
    collector = get_metrics_collector()
    with collector.time_block("planner") as t:
        time.sleep(0.01)
    with collector.time_block("retrieval"):
        time.sleep(0.005)
    collector.record_latency("acquisition", 0.02)
    collector.record_latency("execution", 0.03, failed=True, retries=2)
    collector.incr("failures")
    snap = metrics()
    assert "average_latency" in snap
    assert snap["planner_latency"] >= 0.0
    assert snap["retrieval_latency"] >= 0.0
    assert snap["acquisition_latency"] >= 0.0
    assert snap["execution_latency"] >= 0.0
    assert snap["failures"] >= 1
    assert snap["retries"] >= 2
    assert "memory_usage_mb" in snap
    assert "cpu_usage_percent" in snap


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def test_trace_request_spans():
    with trace_request("api.test", attributes={"path": "/test"}) as ctx:
        assert ctx["request_id"]
        assert ctx["trace_id"]
        assert get_request_id() == ctx["request_id"]
        tracer = get_tracer()
        with tracer.span("planner"):
            with tracer.span("retrieval"):
                pass
    recent = get_tracer().recent(limit=5)
    assert recent
    assert recent[0]["n_spans"] >= 1


# ---------------------------------------------------------------------------
# Request tracker
# ---------------------------------------------------------------------------


def test_request_tracker_lifecycle():
    tracker = get_request_tracker()
    req = tracker.start(path="/chat", method="POST")
    assert tracker.in_flight_count() == 1
    finished = tracker.finish(req.request_id)
    assert finished is not None
    assert finished.status == "completed"
    assert tracker.in_flight_count() == 0
    assert tracker.get(req.request_id) is not None


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


def test_retry_succeeds_after_failures():
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = retry_call(
        flaky,
        RetryPolicy(max_attempts=4, base_delay_seconds=0.001, jitter=False, name="test"),
    )
    assert result == "ok"
    assert state["n"] == 3
    snap = metrics()
    assert snap["retries"] >= 2


def test_retry_exhausts():
    def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        retry_call(
            always_fail,
            RetryPolicy(max_attempts=2, base_delay_seconds=0.001, jitter=False),
        )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens():
    breaker = get_circuit_breaker(
        "test_cb",
        failure_threshold=3,
        recovery_timeout_seconds=0.05,
    )

    def fail():
        raise RuntimeError("down")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(fail)

    assert breaker.state.value == "open"
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "nope")

    time.sleep(0.12)
    # half-open then success closes
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state.value == "closed"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter():
    limiter = get_rate_limiter("test_rl", max_requests=3, window_seconds=60.0)
    assert limiter.allow("user1")
    assert limiter.allow("user1")
    assert limiter.allow("user1")
    assert limiter.allow("user1") is False
    with pytest.raises(RateLimitExceeded):
        limiter.check("user1")
    assert limiter.remaining("user2") == 3


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_config():
    result = validate_config()
    assert result is not None
    d = result.to_dict()
    assert "ok" in d
    assert "issues" in d


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_endpoint_shape():
    report = health(deep=True)
    assert report["status"] in {"healthy", "degraded", "unhealthy"}
    names = {c["name"] for c in report["components"]}
    for required in (
        "registry",
        "library",
        "semantic_db",
        "llm",
        "vector_db",
        "storage",
    ):
        assert required in names
    assert "config" in names  # deep=True


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_exports():
    assert callable(health)
    assert callable(metrics)
    assert callable(trace_request)
    m = metrics()
    assert isinstance(m, dict)
