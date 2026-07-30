"""Regression tests for production ForecastEngine v2."""

from __future__ import annotations

import time
from unittest.mock import patch

import pandas as pd
import pytest

from backend.agents.forecasting_agent import forecasting_agent
from backend.forecast.engine import ForecastEngine, run_forecast
from backend.forecast.strategy import infer_series_profile, select_strategy
from backend.forecast.timeout import run_with_budget


def _yearly_df(n: int = 25) -> pd.DataFrame:
    years = list(range(2000, 2000 + n))
    values = [100 + i * 3.5 + (i % 3) for i in range(n)]
    return pd.DataFrame({"Year": years, "GDP": values})


def _monthly_df(n: int = 48) -> pd.DataFrame:
    dates = pd.date_range("2018-01-01", periods=n, freq="MS")
    # seasonal + trend
    values = [
        50 + 0.2 * i + 8 * ((i % 12) / 12.0) for i in range(n)
    ]
    return pd.DataFrame({"date": dates, "value": values})


def _daily_df(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    values = [10 + 0.05 * i + (i % 7) for i in range(n)]
    return pd.DataFrame({"date": dates, "value": values})


def test_tiny_dataset_uses_trend():
    df = pd.DataFrame({"Year": [2020, 2021, 2022], "value": [1.0, 1.2, 1.5]})
    result = run_forecast(
        df, time_col="Year", value_col="value", horizon=3, budget_seconds=10, use_cache=False
    )
    assert result.success
    assert result.model == "trend"
    assert len(result.forecast) == 3
    assert result.timings.total_ms < 5000


def test_yearly_data_linear_fast():
    df = _yearly_df(20)
    t0 = time.perf_counter()
    result = run_forecast(
        df,
        time_col="Year",
        value_col="GDP",
        horizon=5,
        budget_seconds=10,
        use_cache=False,
    )
    elapsed = time.perf_counter() - t0
    assert result.success
    assert result.model in {"linear", "trend"}
    assert len(result.forecast) == 5
    assert elapsed < 10.0
    assert result.timings.total_ms < 10_000
    assert result.forecast_chart is not None


def test_monthly_data_holt_or_linear():
    df = _monthly_df(48)
    result = run_forecast(
        df,
        time_col="date",
        value_col="value",
        horizon=6,
        budget_seconds=10,
        use_cache=False,
    )
    assert result.success
    assert result.model in {"holt_winters", "linear", "trend"}
    assert len(result.forecast) == 6
    assert result.timings.total_ms < 10_000


def test_missing_values_cleaned():
    df = _yearly_df(15)
    df.loc[3, "GDP"] = None
    df.loc[7, "GDP"] = float("nan")
    result = run_forecast(
        df,
        time_col="Year",
        value_col="GDP",
        horizon=3,
        budget_seconds=10,
        use_cache=False,
    )
    assert result.success
    assert result.n_points >= 10
    assert len(result.forecast) == 3


def test_timeout_returns_partial_trend():
    """Force budget timeout → partial trend projection, never hang."""

    def slow_model(*args, **kwargs):
        time.sleep(5)
        raise RuntimeError("should not reach")

    df = _yearly_df(20)
    engine = ForecastEngine(budget_seconds=0.6, horizon=4)

    with patch("backend.forecast.engine.run_model", side_effect=slow_model):
        # trend fallback after timeout still uses real run_model — patch only primary path
        # Better: make budget expire immediately via slow _fit_predict
        pass

    def slow_fn():
        time.sleep(3)
        return "done"

    budgeted = run_with_budget(slow_fn, budget_seconds=0.4, label="test")
    assert budgeted.timed_out
    assert budgeted.elapsed_seconds < 2.0

    # Engine path: patch run_model for primary call only using a counter
    calls = {"n": 0}
    real_run = __import__("backend.forecast.methods", fromlist=["run_model"]).run_model

    def flaky_run(model, series, horizon, seasonal_period=None):
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(2.5)
            return real_run("linear", series, horizon, seasonal_period=seasonal_period)
        return real_run(model, series, horizon, seasonal_period=seasonal_period)

    with patch("backend.forecast.engine.run_model", side_effect=flaky_run):
        result = ForecastEngine(budget_seconds=0.5, horizon=3).run(
            df,
            time_col="Year",
            value_col="GDP",
            use_cache=False,
        )
    assert result.timed_out or result.success
    # Must return within ~2s and not raise
    assert result.timings.total_ms < 5000
    if result.success:
        assert result.forecast
        assert result.partial or result.model == "trend"


def test_cache_reuse():
    # Unique values so fingerprint is not shared with other tests
    df = pd.DataFrame(
        {
            "Year": list(range(1990, 2010)),
            "GDP": [1000 + i * 17.3 for i in range(20)],
        }
    )
    ref = f"test://forecast-cache-gdp-{time.time_ns()}"
    r1 = run_forecast(
        df,
        time_col="Year",
        value_col="GDP",
        reference=ref,
        horizon=4,
        budget_seconds=10,
        use_cache=True,
    )
    assert r1.success
    # First call may still hit durable cache if fingerprint collides; force cold via use_cache path
    if r1.from_cache:
        r1 = run_forecast(
            df,
            time_col="Year",
            value_col="GDP",
            reference=ref + "-cold",
            horizon=5,  # different params → miss
            budget_seconds=10,
            use_cache=False,
        )
        assert r1.success
        assert not r1.from_cache
        # now warm with same params
        r_warm = run_forecast(
            df,
            time_col="Year",
            value_col="GDP",
            reference=ref + "-cold",
            horizon=5,
            budget_seconds=10,
            use_cache=True,
        )
        assert r_warm.success
        # Put then get
        r1 = run_forecast(
            df,
            time_col="Year",
            value_col="GDP",
            reference=ref + "-cold",
            horizon=5,
            budget_seconds=10,
            use_cache=True,
        )

    t0 = time.perf_counter()
    r2 = run_forecast(
        df,
        time_col="Year",
        value_col="GDP",
        reference=ref if not r1.from_cache else ref + "-cold",
        horizon=4 if not r1.from_cache else 5,
        budget_seconds=10,
        use_cache=True,
    )
    elapsed = time.perf_counter() - t0
    assert r2.success
    assert r2.from_cache
    assert len(r2.forecast) >= 1
    assert elapsed < 2.0


def test_strategy_selection_rules():
    # tiny
    tiny = infer_series_profile(pd.to_datetime(["2020", "2021", "2022"]))
    # force n via profile
    from backend.forecast.strategy import SeriesProfile

    assert select_strategy(SeriesProfile(5, "yearly", None, 365 * 4, True)).model == "trend"
    assert select_strategy(SeriesProfile(20, "yearly", None, 365 * 19, True)).model == "linear"
    assert (
        select_strategy(SeriesProfile(48, "monthly", 12, 365 * 4, True)).model
        == "holt_winters"
    )
    daily = select_strategy(
        SeriesProfile(60, "daily", 7, 60, True),
        prophet_available=True,
        allow_prophet=False,
        budget_seconds=10,
    )
    assert daily.model in {"holt_winters", "linear"}
    unsup = select_strategy(SeriesProfile(1, "unknown", None, 0, True))
    assert unsup.model == "unsupported"


def test_agent_preserves_existing_charts_on_soft_failure():
    df = pd.DataFrame({"Year": [2020], "value": [1.0]})  # too small after rules
    state = {
        "data": df,
        "dataset_profile": {"time_columns": ["Year"], "numeric_columns": ["value"]},
        "charts": [{"id": "existing"}],
        "dataset_url": "tiny",
    }
    # n=1 → unsupported
    out = forecasting_agent(state)
    assert out.get("charts") == [{"id": "existing"}]
    # error set but charts preserved
    assert out.get("forecast_error") or not out.get("forecast")


def test_agent_yearly_success_under_budget():
    df = _yearly_df(25)
    state = {
        "data": df,
        "dataset_profile": {"time_columns": ["Year"], "numeric_columns": ["GDP"]},
        "file_path": "local/india_gdp.csv",
    }
    t0 = time.perf_counter()
    out = forecasting_agent(state)
    elapsed = time.perf_counter() - t0
    assert out.get("forecast")
    assert out.get("forecast_error") in (None, "")
    assert out.get("forecast_model") in {"linear", "trend", "holt_winters"}
    assert out.get("forecast_timings")
    assert elapsed < 10.0
    assert out.get("forecast_chart")


def test_legacy_test_compatibility():
    """Original daily series test still passes with new engine."""
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=20, freq="D"),
            "value": range(20),
        }
    )
    state = {
        "data": df,
        "dataset_profile": {"time_columns": ["date"], "numeric_columns": ["value"]},
        "dataset_url": "test_forecast",
    }
    result = forecasting_agent(state)
    assert isinstance(result.get("forecast"), list)
    assert result.get("forecast")
    assert result.get("forecast_error") in (None, "")
    assert result.get("forecast_chart")
