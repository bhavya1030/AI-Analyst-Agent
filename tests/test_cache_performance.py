"""Cache performance: warm path skips graph; latency + hit ratio targets."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.cache.analysis_cache import get_analysis_cache
from backend.cache.ask_cache import (
    get_ask_cache,
    reset_ask_cache_stats,
    resolve_dataset_fingerprint,
)
from backend.cache.fingerprint import clear_file_fingerprint_cache, fingerprint_file


def _csv(path: Path, seed: int = 1) -> Path:
    df = pd.DataFrame(
        {
            "Year": list(range(2000, 2020)),
            "GDP": [1000 + i * seed * 3 for i in range(20)],
            "Country": ["India"] * 20,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def test_fingerprint_file_uses_mtime_cache(tmp_path):
    clear_file_fingerprint_cache()
    p = _csv(tmp_path / "fp.csv")
    t0 = time.perf_counter()
    a = fingerprint_file(p)
    cold = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    b = fingerprint_file(p)
    warm = (time.perf_counter() - t1) * 1000
    assert a and a == b
    # Warm must be dramatically faster (no re-read of file)
    assert warm < cold or warm < 5.0
    assert warm < 50.0


def test_ask_cache_warm_under_2s_and_hit_fields(tmp_path):
    reset_ask_cache_stats()
    clear_file_fingerprint_cache()
    cache = get_ask_cache()
    p = _csv(tmp_path / f"gdp_{uuid.uuid4().hex[:8]}.csv", seed=7)
    fp = resolve_dataset_fingerprint(file_path=str(p))
    assert fp
    get_analysis_cache().invalidate_fingerprint(fp)

    question = "Analyze India's GDP trend over time"
    payload = {
        "answer": "GDP rose steadily over two decades.",
        "charts": [{"id": "c1", "type": "line", "figure": {"data": [{"y": [1, 2, 3]}], "layout": {}}}],
        "forecast": [{"ds": "2025", "yhat": 1.0}],
        "forecast_chart": {},
        "hypotheses": ["growth continues"],
        "recommended_next_steps": ["forecast next"],
        "detected_patterns": ["upward trend"],
        "insights": ["steady growth"],
        "dataset_topic": "India GDP",
        "dataset_name": "India GDP",
        "dataset_summary": {"rows": 20, "numeric_columns": ["GDP"]},
        "columns": ["Year", "GDP", "Country"],
        "rows": 20,
        "last_intent": "analysis",
        "last_operation": "eda",
        "last_chart_type": "line",
    }

    t_cold = time.perf_counter()
    key = cache.put(fp, question, payload, file_path=str(p), cold_ms=8500.0)
    cold_ms = (time.perf_counter() - t_cold) * 1000
    assert key

    # First get may populate L1 from SQLite
    hit1, meta1 = cache.get(fp, question, file_path=str(p))
    assert hit1 is not None
    assert meta1["cache_hit"] is True

    # Second get is pure L1 — must be << 2s
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        hit, meta = cache.get(fp, question, file_path=str(p))
        times.append((time.perf_counter() - t0) * 1000)
        assert hit is not None
        assert meta["cache_hit"] is True
        assert meta.get("cache_latency_ms") is not None
        assert hit.get("answer")
        assert hit.get("charts")
        assert hit.get("eda")
        assert hit.get("artifacts")
        assert hit.get("session_delta")
        assert hit.get("forecast") is not None

    avg_warm = sum(times) / len(times)
    assert avg_warm < 2000.0, f"avg warm lookup {avg_warm:.1f}ms >= 2000ms"
    assert avg_warm < 100.0, f"expected sub-100ms L1 warm, got {avg_warm:.1f}ms"
    # saved_time relative to recorded cold
    assert meta.get("saved_time_ms") is None or meta["saved_time_ms"] >= 0

    stats = cache.stats()
    assert stats["hit_ratio"] >= 0.8 or stats["hits"] >= 5
    assert stats["target_hit_ratio_pct"] == 80.0

    cache.invalidate_dataset(fp)


def test_ask_cache_hit_skips_pipeline_semantics(tmp_path):
    """Cache hit returns full answer/charts/eda without needing graph recompute."""
    reset_ask_cache_stats()
    clear_file_fingerprint_cache()
    cache = get_ask_cache()
    p = _csv(tmp_path / f"gdp_{uuid.uuid4().hex[:8]}.csv", seed=3)
    fp = resolve_dataset_fingerprint(file_path=str(p))
    get_analysis_cache().invalidate_fingerprint(fp)
    q = "Show GDP chart"
    cache.put(
        fp,
        q,
        {
            "answer": "Chart ready.",
            "charts": [{"type": "line"}],
            "dataset_topic": "gdp",
            "columns": ["Year", "GDP"],
            "rows": 20,
            "insights": ["ok"],
            "detected_patterns": ["trend"],
            "forecast": [{"yhat": 1}],
            "hypotheses": ["h"],
            "recommended_next_steps": ["n"],
            "dataset_summary": {"rows": 20},
        },
        file_path=str(p),
        cold_ms=5000.0,
    )

    body, meta = cache.get(fp, q, file_path=str(p))
    assert body and meta["cache_hit"]
    assert meta["cache_latency_ms"] < 2000
    # Pipeline artifacts present without re-running planner/EDA/forecast
    assert body["answer"] == "Chart ready."
    assert body["charts"]
    assert body["eda"]["detected_patterns"] == ["trend"]
    assert body["artifacts"]["forecast"]
    assert body["session_delta"]["dataset_topic"] == "gdp"
    assert meta.get("saved_time_ms") is None or meta["saved_time_ms"] >= 0
    cache.invalidate_dataset(fp)


def test_record_cached_assistant_turn_is_light():
    from backend.sessions.service import SessionService

    svc = SessionService()
    sid = f"cache-warm-{uuid.uuid4().hex[:10]}"
    uid = f"u-{uuid.uuid4().hex[:6]}"
    svc.create_session(session_id=sid, title="Cache warm", user_id=uid)
    svc.append_user_message(sid, "Analyze GDP", user_id=uid)

    result = {
        "answer": "From cache.",
        "session_delta": {
            "dataset_topic": "India GDP",
            "dataset_name": "India GDP",
            "last_intent": "analysis",
            "last_columns_used": ["Year", "GDP"],
        },
        "charts": [{"huge": "x" * 1000}],
        "dataset_topic": "India GDP",
    }
    t0 = time.perf_counter()
    out = svc.record_cached_assistant_turn(
        sid, question="show chart", result=result, user_id=uid
    )
    ms = (time.perf_counter() - t0) * 1000
    assert out.get("from_cache") is True
    assert out.get("message_id")
    assert ms < 2000.0


def test_hit_ratio_simulation(tmp_path):
    """Cold once + many warm → hit ratio > 80%."""
    reset_ask_cache_stats()
    clear_file_fingerprint_cache()
    cache = get_ask_cache()
    p = _csv(tmp_path / f"hr_{uuid.uuid4().hex[:8]}.csv")
    fp = resolve_dataset_fingerprint(file_path=str(p))
    get_analysis_cache().invalidate_fingerprint(fp)
    q = "correlation of GDP"
    cache.put(
        fp,
        q,
        {
            "answer": "corr ok",
            "charts": [],
            "forecast": [],
            "insights": [],
            "detected_patterns": [],
            "hypotheses": [],
            "recommended_next_steps": [],
            "dataset_topic": "gdp",
            "columns": ["Year", "GDP"],
            "rows": 20,
        },
        file_path=str(p),
        cold_ms=3000,
    )
    # 1 miss (implicit before put doesn't count get) + 9 hits
    for _ in range(9):
        hit, meta = cache.get(fp, q, file_path=str(p))
        assert hit and meta["cache_hit"]
    stats = cache.stats()
    assert stats["hit_ratio"] >= 0.80
    cache.invalidate_dataset(fp)
