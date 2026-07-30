"""Retrieval v3 — parallel providers, timeouts, circuit breaker, ranking."""

from __future__ import annotations

import threading
import time

import pytest

from backend.retrieval.data_providers.base import DatasetCandidate
from backend.retrieval.data_providers.orchestrator import ProviderOrchestrator
from backend.retrieval.data_providers.provider_circuit import (
    get_provider_breaker,
    is_provider_available,
    record_provider_failure,
    record_provider_success,
    reset_provider_circuits,
)
from backend.retrieval.data_providers.ranking import rank_candidates
from backend.retrieval.data_providers.timeout_budget import (
    is_retryable_error,
    new_budget,
    run_with_timeout,
)
from backend.retrieval.data_providers.topic import extract_topic_context


# ── helpers ────────────────────────────────────────────────────────────────


class _BaseFake:
    domains: tuple = ()
    priority = 50

    def supports(self, topic, keywords):
        return True

    def preferred_for(self, topic, keywords):
        return self.priority

    def score_for_context(self, *a, **k):
        return self.priority


class SlowProvider(_BaseFake):
    name = "slow"
    priority = 200

    def __init__(self, delay_s: float = 30.0, candidates=None):
        self.delay_s = delay_s
        self._candidates = candidates or []
        self.calls = 0

    def search(self, topic, keywords, *, limit=5):
        self.calls += 1
        time.sleep(self.delay_s)
        return self._candidates[:limit]


class DeadProvider(_BaseFake):
    name = "dead"
    priority = 150

    def __init__(self, error: Exception | None = None):
        self.error = error or ConnectionResetError("connection reset by peer")
        self.calls = 0

    def search(self, topic, keywords, *, limit=5):
        self.calls += 1
        raise self.error


class FastOkProvider(_BaseFake):
    name = "fast_ok"
    priority = 10

    def __init__(
        self,
        provider_name: str = "fast_ok",
        confidence: float = 0.9,
        delay_s: float = 0.0,
    ):
        self.name = provider_name
        self.confidence = confidence
        self.delay_s = delay_s
        self.calls = 0
        self.call_times: list[float] = []

    def search(self, topic, keywords, *, limit=5):
        self.calls += 1
        self.call_times.append(time.perf_counter())
        if self.delay_s:
            time.sleep(self.delay_s)
        return [
            DatasetCandidate(
                title=f"{self.name} CSV",
                topic=topic,
                download_url=f"https://example.com/{self.name}.csv",
                provider=self.name,
                license="ODC",
                dataset_version="test",
                file_format="csv",
                confidence=self.confidence,
                tags=["live"],
            )
        ]


class EmptyProvider(_BaseFake):
    name = "empty"
    priority = 80

    def search(self, topic, keywords, *, limit=5):
        return []


class NetworkFlakyProvider(_BaseFake):
    """Fails once with network error, then succeeds (retry path)."""

    name = "flaky"
    priority = 100

    def __init__(self):
        self.calls = 0

    def search(self, topic, keywords, *, limit=5):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("temporary connection failure")
        return [
            DatasetCandidate(
                title="Flaky OK",
                topic=topic,
                download_url="https://example.com/flaky.csv",
                provider=self.name,
                file_format="csv",
                confidence=0.85,
            )
        ]


class Html404Provider(_BaseFake):
    name = "html404"
    priority = 120

    def __init__(self):
        self.calls = 0

    def search(self, topic, keywords, *, limit=5):
        self.calls += 1
        raise RuntimeError("HTTP 404 Not Found html login page")


@pytest.fixture(autouse=True)
def _reset_circuits():
    reset_provider_circuits()
    yield
    reset_provider_circuits()


# ── timeout budget unit tests ──────────────────────────────────────────────


def test_run_with_timeout_cancels_slow_fn():
    def slow():
        time.sleep(5)
        return "done"

    value, timed_out, error, elapsed = run_with_timeout(
        slow, timeout_s=0.3, label="slow-test"
    )
    assert value is None
    assert timed_out is True
    assert error and "timeout" in error
    assert elapsed < 1.5


def test_run_with_timeout_returns_fast():
    value, timed_out, error, elapsed = run_with_timeout(
        lambda: 42, timeout_s=2.0, label="fast"
    )
    assert value == 42
    assert not timed_out
    assert error is None
    assert elapsed < 1.0


def test_is_retryable_error_policy():
    assert is_retryable_error("Connection reset by peer")
    assert is_retryable_error("read timed out")
    assert is_retryable_error("503 Service Unavailable")
    assert not is_retryable_error("HTTP 404 Not Found")
    assert not is_retryable_error("401 Unauthorized")
    assert not is_retryable_error("403 Forbidden")
    assert not is_retryable_error("returned HTML login page")
    assert not is_retryable_error("no_candidates")
    assert not is_retryable_error("blocked_url")


def test_budget_remaining_decreases():
    budget = new_budget(provider_timeout_s=5.0, global_budget_s=1.0)
    time.sleep(0.15)
    assert budget.remaining_s < 1.0
    assert budget.provider_wait_s() <= 5.0


# ── parallel + slow provider ───────────────────────────────────────────────


def test_slow_provider_does_not_block_fast_success():
    """Slow provider hangs; fast provider still wins under budgets."""
    slow = SlowProvider(delay_s=3.0)
    fast = FastOkProvider(provider_name="fast_ok", confidence=0.95, delay_s=0.05)

    orch = ProviderOrchestrator(
        providers=[slow, fast],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=0.4,
        global_budget_s=2.0,
        max_parallel=4,
    )
    t0 = time.perf_counter()
    result = orch.resolve("gdp analysis")
    elapsed = time.perf_counter() - t0

    assert result.success
    assert result.candidate is not None
    assert result.candidate.provider == "fast_ok"
    # Must not wait for the 30s slow provider
    assert elapsed < 2.5
    assert result.metrics.get("provider_timeout", {}).get("slow") is True
    assert result.metrics.get("provider_success", {}).get("fast_ok") is True
    assert "provider_latency_ms" in result.metrics
    assert result.metrics.get("retrieval_budget_used", 0) > 0
    assert result.metrics.get("parallel_workers", 0) >= 2


def test_dead_provider_parallel_with_success():
    dead = DeadProvider()
    fast = FastOkProvider(provider_name="world_bank", confidence=0.9)

    orch = ProviderOrchestrator(
        providers=[dead, fast],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=2.0,
        global_budget_s=5.0,
    )
    result = orch.resolve("world population")
    assert result.success
    assert result.candidate.provider == "world_bank"
    assert "dead" in result.providers_tried
    assert result.metrics["provider_success"].get("dead") is False


def test_parallel_success_faster_than_serial_sum():
    """Two delayed providers complete near max(d1,d2) not d1+d2."""
    a = FastOkProvider(provider_name="owid", confidence=0.7, delay_s=0.35)
    b = FastOkProvider(provider_name="fred", confidence=0.8, delay_s=0.35)

    orch = ProviderOrchestrator(
        providers=[a, b],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=3.0,
        global_budget_s=5.0,
        max_parallel=4,
    )
    t0 = time.perf_counter()
    result = orch.resolve("US GDP")
    elapsed = time.perf_counter() - t0

    assert result.success
    # Serial would be ~0.7s; parallel should be closer to 0.35–0.55
    assert elapsed < 0.85, f"expected parallel speedup, got {elapsed:.2f}s"
    assert a.calls == 1 and b.calls == 1


def test_mixed_providers_ranking_picks_highest_confidence_trust():
    low = FastOkProvider(provider_name="huggingface", confidence=0.55)
    high = FastOkProvider(provider_name="world_bank", confidence=0.92)

    orch = ProviderOrchestrator(
        providers=[low, high],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=2.0,
        global_budget_s=5.0,
    )
    result = orch.resolve("India GDP growth")
    assert result.success
    assert result.candidate.provider == "world_bank"
    ranks = result.metrics.get("provider_rank", {})
    assert "world_bank" in ranks


def test_global_budget_never_exceeded():
    providers = [
        SlowProvider(delay_s=3.0),
        SlowProvider(delay_s=3.0),
    ]
    providers[1].name = "slow_b"

    orch = ProviderOrchestrator(
        providers=providers,  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=5.0,
        global_budget_s=0.8,
        max_parallel=4,
    )
    t0 = time.perf_counter()
    result = orch.resolve("anything")
    elapsed = time.perf_counter() - t0

    assert not result.success
    # Allow small overhead for thread scheduling
    assert elapsed < 2.5
    assert result.metrics.get("retrieval_budget_used", 0) <= 2.5
    assert result.graceful_message


def test_all_timeout_graceful():
    orch = ProviderOrchestrator(
        providers=[SlowProvider(delay_s=3.0)],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=0.25,
        global_budget_s=1.0,
    )
    result = orch.resolve("timeout topic")
    assert not result.success
    assert result.metrics["provider_timeout"].get("slow") is True
    assert result.graceful_message


# ── circuit breaker ────────────────────────────────────────────────────────


def test_circuit_breaker_opens_after_three_failures():
    name = "circuit_test_prov"
    assert is_provider_available(name)
    for i in range(3):
        record_provider_failure(name, f"timeout attempt {i}")
    assert not is_provider_available(name)
    status = get_provider_breaker(name).snapshot()
    assert status["state"] == "open"


def test_circuit_breaker_skips_open_provider():
    dead = DeadProvider()
    dead.name = "always_dead"
    # Pre-trip circuit
    for _ in range(3):
        record_provider_failure("always_dead", "connection reset")
    assert not is_provider_available("always_dead")

    fast = FastOkProvider(provider_name="owid", confidence=0.9)
    orch = ProviderOrchestrator(
        providers=[dead, fast],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=1.0,
        global_budget_s=3.0,
    )
    result = orch.resolve("climate co2")
    assert result.success
    assert "always_dead" in result.metrics.get("circuit_skipped", [])
    assert dead.calls == 0  # never invoked
    assert result.candidate.provider == "owid"


def test_circuit_success_resets_failures():
    name = "recover_prov"
    record_provider_failure(name, "timeout")
    record_provider_failure(name, "timeout")
    record_provider_success(name)
    # two more failures should not open yet (threshold 3 consecutive)
    record_provider_failure(name, "timeout")
    record_provider_failure(name, "timeout")
    assert is_provider_available(name)
    record_provider_failure(name, "timeout")
    assert not is_provider_available(name)


def test_orchestrator_trips_circuit_on_repeated_timeouts():
    slow = SlowProvider(delay_s=2.0)
    slow.name = "hang_prov"

    for _ in range(3):
        orch = ProviderOrchestrator(
            providers=[slow],  # type: ignore[list-item]
            validate=False,
            provider_timeout_s=0.2,
            global_budget_s=0.6,
        )
        orch.resolve("hang topic")

    assert not is_provider_available("hang_prov")


# ── retry policy ───────────────────────────────────────────────────────────


def test_retry_network_error_then_success():
    flaky = NetworkFlakyProvider()
    orch = ProviderOrchestrator(
        providers=[flaky],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=3.0,
        global_budget_s=6.0,
    )
    result = orch.resolve("retry topic")
    assert result.success
    assert flaky.calls >= 2  # initial fail + retry


def test_no_retry_on_404_html():
    bad = Html404Provider()
    orch = ProviderOrchestrator(
        providers=[bad],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=2.0,
        global_budget_s=4.0,
    )
    result = orch.resolve("bad topic")
    assert not result.success
    # Single call — no retry for 404/html/login
    assert bad.calls == 1


# ── ranking ────────────────────────────────────────────────────────────────


def test_rank_candidates_prefers_trust_and_confidence():
    ctx = extract_topic_context("India GDP growth 2000-2024")
    cands = [
        DatasetCandidate(
            title="HF misc",
            topic="gdp",
            download_url="https://x/a.csv",
            provider="huggingface",
            confidence=0.6,
        ),
        DatasetCandidate(
            title="World Bank GDP India",
            topic="gdp",
            download_url="https://x/b.csv",
            provider="world_bank",
            confidence=0.9,
            country=["India"],
            metric="GDP",
            tags=["live"],
        ),
    ]
    ranked = rank_candidates(cands, ctx)
    assert ranked[0][1].provider == "world_bank"
    assert ranked[0][0] > ranked[1][0]


# ── metrics contract ───────────────────────────────────────────────────────


def test_metrics_fields_present_on_success_and_miss():
    ok = FastOkProvider(provider_name="fred", confidence=0.88)
    orch = ProviderOrchestrator(
        providers=[ok],  # type: ignore[list-item]
        validate=False,
        provider_timeout_s=2.0,
        global_budget_s=5.0,
    )
    result = orch.resolve("US unemployment")
    assert result.success
    m = result.metrics
    for key in (
        "provider_latency_ms",
        "provider_timeout",
        "provider_rank",
        "provider_success",
        "retrieval_budget_used",
    ):
        assert key in m, f"missing metric {key}"

    empty = EmptyProvider()
    orch2 = ProviderOrchestrator(
        providers=[empty],  # type: ignore[list-item]
        validate=False,
    )
    miss = orch2.resolve("unknown xyzzy")
    assert not miss.success
    assert "retrieval_budget_used" in miss.metrics


# ── p95-style wall clock under concurrency ─────────────────────────────────


def test_p95_retrieval_under_10s_with_hanging_peers():
    """Target: p95 retrieval < 10s even with hanging providers."""
    hangers = []
    for i in range(4):
        p = SlowProvider(delay_s=3.0)
        p.name = f"hang_{i}"
        hangers.append(p)
    winner = FastOkProvider(provider_name="github_raw", confidence=0.91, delay_s=0.05)

    samples = []
    for _ in range(5):
        reset_provider_circuits()
        orch = ProviderOrchestrator(
            providers=hangers + [winner],  # type: ignore[list-item]
            validate=False,
            provider_timeout_s=5.0,
            global_budget_s=12.0,
            max_parallel=8,
        )
        t0 = time.perf_counter()
        result = orch.resolve("open gdp csv")
        samples.append(time.perf_counter() - t0)
        assert result.success

    samples.sort()
    p95 = samples[-1]  # n=5 → max as p95 proxy
    assert p95 < 10.0, f"p95 {p95:.2f}s exceeds 10s target"
    assert max(samples) < 12.0
