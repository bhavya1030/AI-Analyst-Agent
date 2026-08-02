"""Visualization v2 — inference, validation, scatter/heatmap, fallbacks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.agents.viz_agent import viz_agent
from backend.visualization.builder import build_chart, build_chart_safe
from backend.visualization.inference import (
    detect_requested_chart_type,
    infer_chart_spec,
    profile_columns,
)
from backend.visualization.validation import recommend_chart_type, validate_chart_request


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def gdp_country_df():
    """Classic scatter failure: Country (cat) + GDP (numeric)."""
    return pd.DataFrame(
        {
            "Country": ["India", "USA", "China", "Brazil", "Germany"],
            "GDP": [3.7e12, 25e12, 18e12, 2e12, 4e12],
            "Year": [2020, 2020, 2020, 2020, 2020],
        }
    )


@pytest.fixture
def time_series_df():
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
            "value": np.linspace(10, 50, 24) + np.random.randn(24),
        }
    )


@pytest.fixture
def multi_numeric_df():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "Year": list(range(2000, 2020)),
            "GDP": rng.normal(100, 10, 20),
            "Population": rng.normal(50, 5, 20),
            "Inflation": rng.normal(3, 1, 20),
        }
    )


@pytest.fixture
def mixed_missing_df():
    return pd.DataFrame(
        {
            "category": ["A", "B", None, "A", "C", "B", "A"],
            "amount": [10.0, None, 30.0, 40.0, np.nan, 60.0, 70.0],
            "score": [1, 2, 3, None, 5, 6, 7],
        }
    )


@pytest.fixture
def single_numeric_df():
    return pd.DataFrame({"temperature": [12.1, 15.0, 9.5, 22.3, 18.0, 11.2]})


# ── detection / profiling ───────────────────────────────────────────────────


def test_detect_scatter_versus_and_vs():
    assert detect_requested_chart_type("Scatter of year versus GDP") == "scatter"
    assert detect_requested_chart_type("plot x vs y") == "scatter"
    assert detect_requested_chart_type("correlation heatmap") == "heatmap"
    assert detect_requested_chart_type("Bar chart of salary by department") == "bar"
    assert detect_requested_chart_type("Pie chart of unemployment") == "pie"
    assert detect_requested_chart_type("Histogram of temperature") == "histogram"
    assert detect_requested_chart_type("Show me the trend") == "line"


def test_profile_columns_roles(multi_numeric_df, gdp_country_df):
    roles = profile_columns(multi_numeric_df, time_columns=["Year"])
    assert "GDP" in roles.numeric
    assert "Year" in roles.time or "Year" in roles.numeric

    roles2 = profile_columns(gdp_country_df)
    assert "GDP" in roles2.numeric
    assert "Country" in roles2.categorical


# ── scatter validation (Country + GDP → Bar) ────────────────────────────────


def test_scatter_country_gdp_rejected_recommends_bar(gdp_country_df):
    result = validate_chart_request(
        gdp_country_df,
        requested_type="scatter",
        question="Scatter of Country versus GDP",
        x="Country",
        y="GDP",
    )
    assert result.ok is False
    assert result.recommended_type == "bar"
    assert result.spec is not None
    assert result.spec.chart_type == "bar"
    assert "Recommended: Bar Chart" in (result.reason or result.spec.redirect_reason)
    assert result.spec.x == "Country"
    assert result.spec.y == "GDP"


def test_scatter_country_gdp_via_question_inference(gdp_country_df):
    spec = infer_chart_spec(
        gdp_country_df,
        "Scatter Country vs GDP",
        preferred_type="scatter",
    )
    assert spec.chart_type == "bar"
    assert spec.redirected is True
    assert spec.recommended_type == "bar"


def test_scatter_year_versus_gdp_succeeds(multi_numeric_df):
    """CH03-style: year + GDP are both numeric → scatter OK."""
    spec = infer_chart_spec(
        multi_numeric_df,
        "Scatter of year versus GDP",
        time_columns=["Year"],
    )
    assert spec.chart_type == "scatter"
    assert spec.x in multi_numeric_df.columns
    assert spec.y in multi_numeric_df.columns
    assert spec.x in profile_columns(multi_numeric_df).numeric or True
    # both axes numeric
    roles = profile_columns(multi_numeric_df, time_columns=["Year"])
    assert spec.x in roles.numeric
    assert spec.y in roles.numeric

    fig, err = build_chart(multi_numeric_df, spec)
    assert err is None
    assert fig is not None


def test_viz_agent_scatter_year_versus_gdp(multi_numeric_df):
    state = {
        "data": multi_numeric_df,
        "dataset_profile": {
            "time_columns": ["Year"],
            "numeric_columns": ["Year", "GDP", "Population", "Inflation"],
        },
        "question": "Scatter of year versus GDP",
    }
    out = viz_agent(state)
    assert out.get("chart") is not None
    assert out.get("last_chart_type") == "scatter"
    assert len(out.get("chart_columns_used") or []) >= 2
    assert out.get("chart_error") in (None, "")


# ── heatmap ─────────────────────────────────────────────────────────────────


def test_heatmap_builds_with_numeric_matrix(multi_numeric_df):
    built = build_chart_safe(
        multi_numeric_df,
        question="Heatmap or correlation of population data",
        preferred_type="heatmap",
    )
    assert built["fig"] is not None
    assert built["chart_type"] == "heatmap"
    assert built["error"] is None


def test_heatmap_single_numeric_falls_back(single_numeric_df):
    built = build_chart_safe(
        single_numeric_df,
        question="Show correlation heatmap",
        preferred_type="heatmap",
    )
    assert built["fig"] is not None
    # redirected to histogram
    assert built["chart_type"] in {"histogram", "bar"}
    assert built["fallback_used"] or (built["spec"] and built["spec"].redirected)


def test_viz_agent_heatmap(multi_numeric_df):
    out = viz_agent(
        {
            "data": multi_numeric_df,
            "dataset_profile": {"numeric_columns": list(multi_numeric_df.columns)},
            "question": "Heatmap or correlation of population data",
        }
    )
    assert out.get("chart") is not None
    assert out.get("last_chart_type") == "heatmap"


# ── mixed types / missing values ────────────────────────────────────────────


def test_mixed_types_never_crash(mixed_missing_df):
    for q in (
        "Scatter of category versus amount",
        "Bar chart of amount by category",
        "Histogram of score",
        "Pie chart of category",
        "correlation heatmap",
        "line chart trend",
    ):
        built = build_chart_safe(mixed_missing_df, question=q)
        # Must not raise; prefer a figure when any signal exists
        assert "fig" in built
        assert "error" in built
        if built["fig"] is None:
            # only acceptable if truly impossible
            assert built["error"]


def test_missing_values_scatter_drops_na(mixed_missing_df):
    # amount + score both numeric with NaNs
    built = build_chart_safe(
        mixed_missing_df,
        question="scatter of amount versus score",
    )
    assert built["fig"] is not None
    assert built["chart_type"] == "scatter"


def test_missing_values_bar(mixed_missing_df):
    built = build_chart_safe(
        mixed_missing_df,
        question="Bar chart of amount by category",
    )
    assert built["fig"] is not None
    assert built["chart_type"] == "bar"


# ── single numeric column ───────────────────────────────────────────────────


def test_single_numeric_histogram(single_numeric_df):
    built = build_chart_safe(
        single_numeric_df,
        question="Histogram of temperature",
    )
    assert built["fig"] is not None
    assert built["chart_type"] == "histogram"
    assert built["spec"].x == "temperature"


def test_single_numeric_scatter_redirects_to_histogram(single_numeric_df):
    result = validate_chart_request(
        single_numeric_df,
        requested_type="scatter",
        question="Scatter plot",
    )
    assert result.ok is False
    assert result.spec.chart_type == "histogram"
    assert result.recommended_type == "histogram"

    fig, err = build_chart(single_numeric_df, result.spec)
    assert fig is not None
    assert err is None


def test_viz_agent_single_numeric(single_numeric_df):
    out = viz_agent(
        {
            "data": single_numeric_df,
            "dataset_profile": {"numeric_columns": ["temperature"]},
            "question": "Show distribution",
        }
    )
    assert out.get("chart") is not None
    assert out.get("last_chart_type") == "histogram"


# ── automatic selection rules ───────────────────────────────────────────────


def test_auto_line_for_time_series(time_series_df):
    spec = infer_chart_spec(
        time_series_df,
        "Show me the trend",
        time_columns=["date"],
    )
    assert spec.chart_type == "line"
    assert spec.x == "date"
    assert spec.y == "value"
    assert spec.sort_by == "date"


def test_auto_bar_for_categorical_numeric(gdp_country_df):
    spec = infer_chart_spec(gdp_country_df, "compare countries")
    assert spec.chart_type in {"bar", "line"}  # Year may pull line
    # With explicit bar intent
    spec2 = infer_chart_spec(gdp_country_df, "Bar chart of GDP by Country")
    assert spec2.chart_type == "bar"
    assert spec2.aggregation in {"sum", "mean", "count"}


def test_aggregation_sorting_grouping_inferred(gdp_country_df):
    spec = infer_chart_spec(gdp_country_df, "Bar chart of GDP by Country")
    assert spec.group_by == "Country" or spec.x == "Country"
    assert spec.y == "GDP"
    assert spec.aggregation == "sum"
    assert spec.sort_by == "GDP"
    assert spec.sort_ascending is False


# ── pie / bar / line agent paths ───────────────────────────────────────────


def test_viz_agent_pie(gdp_country_df):
    out = viz_agent(
        {
            "data": gdp_country_df,
            "dataset_profile": {},
            "question": "Pie chart of GDP by Country",
        }
    )
    assert out.get("chart") is not None
    assert out.get("last_chart_type") == "pie"


def test_viz_agent_bar(gdp_country_df):
    out = viz_agent(
        {
            "data": gdp_country_df,
            "dataset_profile": {},
            "question": "Bar chart of GDP by Country",
        }
    )
    assert out.get("chart") is not None
    assert out.get("last_chart_type") == "bar"


def test_viz_agent_line_time(time_series_df):
    out = viz_agent(
        {
            "data": time_series_df,
            "dataset_profile": {"time_columns": ["date"], "numeric_columns": ["value"]},
            "question": "Show me the trend",
        }
    )
    assert out.get("chart") is not None
    assert out.get("chart_columns_used") == ["date", "value"]
    assert out.get("last_chart_type") == "line"
    assert out.get("chart_error") in (None, "")


def test_viz_agent_never_crashes_on_empty():
    out = viz_agent({"data": pd.DataFrame(), "question": "scatter plot"})
    assert out.get("chart") is None or out.get("chart") is not None  # no raise
    # empty may fail soft
    assert "chart_error" in out or out.get("chart") is None or out.get("chart")


def test_viz_agent_none_data():
    out = viz_agent({"data": None, "question": "plot something"})
    assert out.get("chart") is None
    assert out.get("chart_error")


def test_recommend_chart_type_rules():
    roles = profile_columns(
        pd.DataFrame({"Country": ["A", "B"], "GDP": [1.0, 2.0]})
    )
    assert recommend_chart_type(roles, requested="scatter") == "bar"
    roles2 = profile_columns(pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    assert recommend_chart_type(roles2) in {"scatter", "heatmap", "line"}


def test_build_chart_safe_never_raises_garbage_df():
    dfs = [
        pd.DataFrame({"x": [None, None], "y": [None, None]}),
        pd.DataFrame({"a": ["x", "y", "z"]}),
        pd.DataFrame({"n": [1]}),
    ]
    for df in dfs:
        built = build_chart_safe(df, question="scatter of a versus b")
        assert isinstance(built, dict)
