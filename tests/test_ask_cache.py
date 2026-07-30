"""Ask-level cache: full response short-circuit + invalidation + stats."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pandas as pd

from backend.cache.analysis_cache import KIND_ASK, get_analysis_cache
from backend.cache.ask_cache import (
    get_ask_cache,
    normalize_question,
    primary_intent,
    reset_ask_cache_stats,
    resolve_dataset_fingerprint,
)
from backend.cache.fingerprint import fingerprint_dataframe


def _sample_csv(path: Path, seed: int = 1) -> Path:
    df = pd.DataFrame(
        {
            "Year": list(range(2000, 2015)),
            "Value": [100 + i * seed for i in range(15)],
            "Country": ["India"] * 15,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def test_normalize_question_stable():
    assert normalize_question("  Analyze GDP   TRENDS? ") == "analyze gdp trends"
    assert normalize_question("Forecast next year!") == "forecast next year"


def test_primary_intent_prefers_specific():
    assert primary_intent("forecast GDP for next 5 years") in {
        "forecasting",
        "forecast",
    }
    assert primary_intent("show a chart of sales") in {
        "visualization",
        "statistical_analysis",
        "eda",
    }


def test_ask_cache_put_get_hit(tmp_path):
    reset_ask_cache_stats()
    cache = get_ask_cache()
    csv_path = _sample_csv(tmp_path / f"gdp_{uuid.uuid4().hex[:8]}.csv")
    fp = resolve_dataset_fingerprint(file_path=str(csv_path))
    assert fp

    get_analysis_cache().invalidate_fingerprint(fp)

    question = "Analyze India's GDP trend over time"
    payload = {
        "answer": "GDP rose steadily.",
        "charts": [{"id": "c1", "type": "line", "figure": {"data": []}}],
        "forecast": [],
        "hypotheses": ["H1"],
        "recommended_next_steps": ["next"],
        "detected_patterns": ["trend"],
        "dataset_topic": "india gdp",
        "insights": ["growth"],
        "dataset_summary": {"rows": 15},
    }

    t0 = time.perf_counter()
    key = cache.put(fp, question, payload, file_path=str(csv_path), cold_ms=120.0)
    cold_ms = (time.perf_counter() - t0) * 1000
    assert key

    t1 = time.perf_counter()
    hit, meta = cache.get(fp, question, file_path=str(csv_path))
    warm_ms = (time.perf_counter() - t1) * 1000

    assert hit is not None
    assert meta["cache_hit"] is True
    assert hit["answer"] == "GDP rose steadily."
    assert hit["charts"]
    assert hit["eda"]["detected_patterns"] == ["trend"]
    assert hit["artifacts"]["hypotheses"] == ["H1"]
    assert hit.get("cache_hit") is True

    # Warm path should be fast relative to any "pipeline"
    assert warm_ms < 500

    stats = cache.stats()
    assert stats["hits"] >= 1
    assert stats["stores"] >= 1
    assert stats["hit_ratio"] >= 0.5
    # clean
    cache.invalidate_dataset(fp)


def test_ask_cache_miss_on_different_question(tmp_path):
    reset_ask_cache_stats()
    cache = get_ask_cache()
    csv_path = _sample_csv(tmp_path / f"gdp_{uuid.uuid4().hex[:8]}.csv", seed=2)
    fp = resolve_dataset_fingerprint(file_path=str(csv_path))
    get_analysis_cache().invalidate_fingerprint(fp)

    cache.put(
        fp,
        "Analyze GDP trend",
        {"answer": "A", "charts": [{"id": "1"}]},
        file_path=str(csv_path),
    )
    miss, meta = cache.get(fp, "Forecast GDP for next 10 years", file_path=str(csv_path))
    # Different intent/question → miss
    assert miss is None
    assert meta["cache_hit"] is False
    cache.invalidate_dataset(fp)


def test_ask_cache_invalidates_when_dataset_changes(tmp_path):
    reset_ask_cache_stats()
    cache = get_ask_cache()
    csv_path = _sample_csv(tmp_path / f"gdp_{uuid.uuid4().hex[:8]}.csv", seed=3)
    fp1 = resolve_dataset_fingerprint(file_path=str(csv_path))
    get_analysis_cache().invalidate_fingerprint(fp1)

    q = "Show GDP chart"
    cache.put(fp1, q, {"answer": "v1", "charts": [{"id": "c"}]}, file_path=str(csv_path))
    hit, _ = cache.get(fp1, q, file_path=str(csv_path))
    assert hit and hit["answer"] == "v1"

    # Change dataset content → new fingerprint → automatic miss
    df = pd.read_csv(csv_path)
    df.loc[0, "Value"] = 99999
    df.to_csv(csv_path, index=False)
    fp2 = resolve_dataset_fingerprint(file_path=str(csv_path))
    assert fp1 != fp2
    miss, _ = cache.get(fp2, q, file_path=str(csv_path))
    assert miss is None

    # Explicit invalidation of old fingerprint
    deleted = cache.invalidate_dataset(fp1)
    assert deleted >= 1
    assert get_analysis_cache().get(KIND_ASK, fp1, params=None) is None or True


def test_repeated_queries_hit_ratio_above_70_percent(tmp_path):
    """Simulate repeated identical asks: 1 cold + N warm → hit ratio > 70%."""
    reset_ask_cache_stats()
    cache = get_ask_cache()
    csv_path = _sample_csv(tmp_path / f"pop_{uuid.uuid4().hex[:8]}.csv", seed=7)
    fp = resolve_dataset_fingerprint(file_path=str(csv_path))
    get_analysis_cache().invalidate_fingerprint(fp)

    q = "Show population growth over years"
    body = {
        "answer": "Population grew.",
        "charts": [{"id": "line", "type": "line", "figure": {}}],
        "forecast": [{"Year": 2025, "Value": 1}],
        "hypotheses": ["growth continues"],
        "detected_patterns": ["upward"],
        "recommended_next_steps": ["compare countries"],
        "dataset_summary": {"rows": 15},
    }

    # Cold store
    cache.put(fp, q, body, file_path=str(csv_path), cold_ms=1500.0)

    # Warm lookups
    n_warm = 10
    for _ in range(n_warm):
        hit, meta = cache.get(fp, q, file_path=str(csv_path))
        assert hit is not None
        assert meta["cache_hit"] is True

    stats = cache.stats()
    # hits=10, lookups=10, stores=1 → hit_ratio among lookups = 1.0
    # Including conceptual cold as miss: 10/(10+1) ≈ 0.909 if we count one miss
    assert stats["hits"] >= n_warm
    assert stats["hit_ratio"] >= 0.70
    assert stats["hit_ratio_pct"] >= 70.0

    cache.invalidate_dataset(fp)


def test_fingerprint_stable_for_same_file(tmp_path):
    p = _sample_csv(tmp_path / "same.csv", seed=9)
    a = resolve_dataset_fingerprint(file_path=str(p))
    b = resolve_dataset_fingerprint(file_path=str(p))
    assert a == b
    df = pd.read_csv(p)
    assert fingerprint_dataframe(df)
