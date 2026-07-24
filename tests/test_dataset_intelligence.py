"""Tests for Dataset Intelligence Service (structure only)."""

from pathlib import Path

import pytest

from backend.intelligence import (
    DatasetIntelligenceService,
    DatasetProfile,
    IntelligenceValidationError,
    LLMProfiler,
    RuleBasedProfiler,
    profile_dataset,
    set_default_profiler,
)


def test_profile_time_series_csv(tmp_path):
    path = tmp_path / "india_gdp.csv"
    path.write_text(
        "Country Name,Year,Value\n"
        "India,2019,2.8e12\n"
        "India,2020,2.7e12\n"
        "India,2021,3.1e12\n"
        "China,2019,14e12\n"
        "China,2020,14.7e12\n",
        encoding="utf-8",
    )
    profile = profile_dataset(path)
    assert isinstance(profile, DatasetProfile)
    assert profile.row_count == 5
    assert "Year" in profile.column_names
    assert profile.time_column in {"Year", "year"} or profile.time_column == "Year"
    assert "Value" in profile.numeric_metrics or any(
        c in profile.numeric_metrics for c in ("Value",)
    )
    assert profile.dataset_type in {"time_series", "tabular"}
    assert profile.domain in {"economics", "finance", "general", "demographics"}
    assert profile.profiler == "rule_based"
    # No EDA-style stats keys
    d = profile.to_dict()
    assert "mean" not in d
    assert "std" not in d
    assert "chart" not in d


def test_profile_missing_file():
    with pytest.raises(IntelligenceValidationError):
        profile_dataset("/nonexistent/path/file.csv")


def test_llm_profiler_swap(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,price\n2020-01-01,10\n2020-01-02,11\n", encoding="utf-8")
    set_default_profiler(LLMProfiler())
    try:
        profile = DatasetIntelligenceService().profile_dataset(path)
        assert profile.profiler == "llm"
        assert profile.time_column is not None or "date" in [c.lower() for c in profile.column_names]
    finally:
        set_default_profiler(RuleBasedProfiler())


def test_module_level_use_llm_flag(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    profile = profile_dataset(path, use_llm=True)
    assert profile.profiler == "llm"
