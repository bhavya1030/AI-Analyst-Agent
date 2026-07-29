"""Phase 2: durable AnalysisCache + agent integration tests."""

from __future__ import annotations

import uuid

import pandas as pd

from backend.agents.dataset_profile_agent import dataset_profile_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.viz_agent import viz_agent
from backend.cache.analysis_cache import (
    KIND_CHART,
    KIND_EDA,
    KIND_EMBEDDING,
    KIND_FORECAST,
    KIND_PROFILE,
    get_analysis_cache,
)
from backend.cache.fingerprint import (
    compute_dataset_fingerprint,
    fingerprint_dataframe,
)


def _df_gdp(seed: int | None = None) -> pd.DataFrame:
    """Unique seed keeps fingerprints isolated across tests / prior runs."""
    if seed is None:
        seed = int(uuid.uuid4().hex[:8], 16) % 10_000
    return pd.DataFrame(
        {
            "Year": list(range(2000, 2020)),
            "Value": [float(i * 10 + 3 + seed) for i in range(20)],
            "Country": ["India"] * 20,
            "Seed": [seed] * 20,
        }
    )


def test_fingerprint_changes_when_data_changes():
    a = _df_gdp()
    b = a.copy()
    assert fingerprint_dataframe(a) == fingerprint_dataframe(b)

    b.loc[0, "Value"] = 99999.0
    assert fingerprint_dataframe(a) != fingerprint_dataframe(b)


def test_durable_profile_and_eda_cache_hit():
    df = _df_gdp()
    fp = compute_dataset_fingerprint(df)

    # Ensure clean miss for this unique fingerprint
    get_analysis_cache().invalidate_fingerprint(fp)

    state1 = {"data": df, "dataset_url": None, "file_path": None}
    state1 = dataset_profile_agent(state1)
    assert state1.get("dataset_profile")
    assert state1.get("profile_from_cache") is False
    assert state1.get("dataset_fingerprint") == fp

    # Second run must hit durable cache
    state2 = {"data": df}
    state2 = dataset_profile_agent(state2)
    assert state2.get("profile_from_cache") is True
    assert state2["dataset_profile"]["rows"] == 20
    assert "Year" in state2["dataset_profile"]["time_columns"]

    # EDA
    s1 = eda_agent({"data": df, "dataset_fingerprint": fp})
    assert s1.get("eda_from_cache") is False
    s2 = eda_agent({"data": df, "dataset_fingerprint": fp})
    assert s2.get("eda_from_cache") is True

    from backend.config import settings

    emb = get_analysis_cache().get(
        KIND_EMBEDDING,
        fp,
        params={"model": settings.EMBEDDING_MODEL_NAME},
    )
    assert emb is not None
    assert "vector" in emb


def test_cache_invalidates_on_fingerprint_change():
    cache = get_analysis_cache()
    df = _df_gdp()
    fp1 = fingerprint_dataframe(df)
    cache.put(KIND_EDA, fp1, {"rows": 20, "marker": "v1"})

    hit = cache.get(KIND_EDA, fp1)
    assert hit and hit.get("marker") == "v1"

    df2 = df.copy()
    df2.loc[0, "Value"] = -1.0
    fp2 = fingerprint_dataframe(df2)
    assert fp1 != fp2
    assert cache.get(KIND_EDA, fp2) is None


def test_viz_agent_uses_durable_chart_cache():
    df = _df_gdp()
    fp = compute_dataset_fingerprint(df)
    get_analysis_cache().invalidate_fingerprint(fp)

    profile_state = dataset_profile_agent({"data": df, "dataset_fingerprint": fp})
    profile = profile_state["dataset_profile"]

    state = {
        "data": df,
        "question": "show trend",
        "dataset_profile": profile,
        "dataset_fingerprint": fp,
    }
    out1 = viz_agent(dict(state))
    assert out1.get("chart") is not None
    assert out1.get("chart_from_cache") is False

    out2 = viz_agent(dict(state))
    assert out2.get("chart") is not None
    assert out2.get("chart_from_cache") is True
    assert out2.get("last_chart_type") == out1.get("last_chart_type")


def test_forecast_cache_roundtrip_without_prophet_path():
    """Store/retrieve forecast payload via AnalysisCache service directly."""
    cache = get_analysis_cache()
    fp = f"test-fp-{uuid.uuid4().hex[:12]}"
    params = {"target": "Value", "time_col": "Year", "horizon": 10, "model": "regression"}
    payload = {
        "forecast": [{"ds": "2021-01-01", "yhat": 1.0}],
        "forecast_chart": {"data": [], "layout": {}},
    }
    cache.put(KIND_FORECAST, fp, payload, params)
    hit = cache.get(KIND_FORECAST, fp, params)
    assert hit is not None
    assert hit["forecast"][0]["yhat"] == 1.0


def test_get_or_compute_only_runs_once():
    cache = get_analysis_cache()
    fp = f"goc-{uuid.uuid4().hex[:12]}"
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"ok": True, "n": calls["n"]}

    r1, hit1 = cache.get_or_compute(KIND_PROFILE, fp, compute)
    r2, hit2 = cache.get_or_compute(KIND_PROFILE, fp, compute)
    assert hit1 is False
    assert hit2 is True
    assert r1 == r2
    assert calls["n"] == 1
