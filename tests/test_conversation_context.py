"""Tests for Conversation Context Manager (Task 16)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.context import (
    AnalysisStep,
    ContextExpiredError,
    ContextNotFoundError,
    ContextValidationError,
    ConversationContext,
    ConversationContextManager,
    ConversationMemoryStore,
    DatasetRef,
    FilterSpec,
    ReferenceKind,
    ResolvedRequest,
    VisualizationRef,
    clear_context,
    load_context,
    reset_context_manager,
    resolve_reference,
    save_context,
    update_context,
)


@pytest.fixture(autouse=True)
def _clean_manager():
    reset_context_manager()
    yield
    reset_context_manager()


# ---------------------------------------------------------------------------
# Memory store
# ---------------------------------------------------------------------------


def test_store_multi_conversations():
    store = ConversationMemoryStore(ttl_seconds=600)
    a = ConversationContext(conversation_id="c1", last_question="q1")
    b = ConversationContext(conversation_id="c2", last_question="q2")
    store.put(a)
    store.put(b)
    assert store.count() == 2
    assert store.get("c1").last_question == "q1"
    assert store.get("c2").last_question == "q2"
    assert set(store.list_ids()) == {"c1", "c2"}


def test_store_expiry():
    store = ConversationMemoryStore(ttl_seconds=1)
    ctx = ConversationContext(conversation_id="exp1")
    # Force old activity
    old = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(microsecond=0).isoformat()
    ctx.last_activity_at = old
    ctx.updated_at = old
    store.put(ctx)
    # put() touches — so set again after put
    stored = store.get("exp1", touch=False)
    stored.last_activity_at = old
    stored.updated_at = old
    store._store["exp1"] = stored  # direct for test

    with pytest.raises(ContextExpiredError):
        store.get("exp1", touch=False, raise_if_expired=True)


def test_store_delete():
    store = ConversationMemoryStore()
    store.put(ConversationContext(conversation_id="d1"))
    assert store.delete("d1") is True
    assert store.delete("d1") is False


# ---------------------------------------------------------------------------
# Manager CRUD
# ---------------------------------------------------------------------------


def test_save_load_update_clear():
    mgr = ConversationContextManager(ttl_seconds=600)
    ctx = ConversationContext(
        conversation_id="s1",
        metrics=["GDP"],
        selected_countries=["India"],
    )
    mgr.save_context("s1", ctx)
    loaded = mgr.load_context("s1")
    assert loaded.metrics == ["GDP"]
    assert loaded.selected_countries == ["India"]

    mgr.update_context(
        "s1",
        countries=["China"],
        append_countries=True,
        metrics=["Population"],
        append_metrics=True,
    )
    loaded2 = mgr.load_context("s1")
    assert "India" in loaded2.selected_countries
    assert "China" in loaded2.selected_countries
    assert "GDP" in loaded2.metrics
    assert "Population" in loaded2.metrics

    assert mgr.clear_context("s1") is True
    with pytest.raises(ContextNotFoundError):
        mgr.load_context("s1")


def test_module_level_api():
    save_context(
        "m1",
        {
            "conversation_id": "m1",
            "metrics": ["GDP"],
            "selected_countries": ["India"],
            "active_datasets": [
                {"topic": "India GDP", "local_path": "/tmp/gdp.csv", "is_active": True}
            ],
        },
    )
    ctx = load_context("m1")
    assert ctx.primary_topic() == "India GDP"
    update_context("m1", operation="analyze", question="Analyze India's GDP")
    ctx2 = load_context("m1")
    assert ctx2.last_operation == "analyze"
    assert clear_context("m1") is True


def test_does_not_store_dataframes():
    mgr = ConversationContextManager()
    df = pd.DataFrame({"a": [1, 2]})
    # Patch / save with dataframe-like keys must be stripped
    mgr.save_context(
        "df1",
        {
            "conversation_id": "df1",
            "data": df,
            "merged_dataframe": df,
            "metrics": ["X"],
            "metadata": {"data": df, "ok": True},
        },
    )
    ctx = mgr.load_context("df1")
    d = ctx.to_dict()
    assert "data" not in d
    assert d["metrics"] == ["X"]
    assert "data" not in d["metadata"]
    assert d["metadata"].get("ok") is True

    # update with dataset dict containing df key
    mgr.update_context(
        "df1",
        dataset={"topic": "T", "local_path": "/x.csv", "data": df, "dataframe": df},
    )
    ctx2 = mgr.load_context("df1")
    assert ctx2.active_datasets[0].topic == "T"
    assert "data" not in ctx2.active_datasets[0].to_dict()


def test_record_dataset_filter_viz_analysis():
    mgr = ConversationContextManager()
    mgr.record_dataset(
        "r1",
        topic="India GDP",
        local_path="/data/gdp.csv",
        dataset_id="ds-1",
        columns=["Country", "Year", "Value"],
        row_count=100,
    )
    mgr.record_filter("r1", column="Year", operator="gt", value=2010, label="Year > 2010")
    mgr.record_visualization(
        "r1",
        chart_type="line",
        columns=["Year", "Value"],
        title="India GDP Trend",
    )
    mgr.record_analysis(
        "r1",
        question="Analyze India's GDP",
        operation="analyze",
        intent="eda",
        summary="GDP trend analyzed",
        countries=["India"],
        metrics=["GDP"],
        dataset_topics=["India GDP"],
    )
    ctx = mgr.load_context("r1")
    assert ctx.active_dataset().topic == "India GDP"
    assert ctx.filters[0].label == "Year > 2010"
    assert ctx.last_chart().chart_type == "line"
    assert ctx.last_analysis().operation == "analyze"
    assert "India" in ctx.selected_countries
    assert "GDP" in ctx.metrics


def test_create_if_missing():
    mgr = ConversationContextManager()
    ctx = mgr.load_context("new-id", create_if_missing=True)
    assert ctx.conversation_id == "new-id"


def test_validation_empty_id():
    mgr = ConversationContextManager()
    with pytest.raises(ContextValidationError):
        mgr.save_context("", ConversationContext(conversation_id="x"))


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------


def _seed_india_gdp(mgr: ConversationContextManager, cid: str = "conv1") -> None:
    mgr.record_dataset(
        cid,
        topic="India GDP",
        local_path="/data/india_gdp.csv",
        columns=["Country", "Year", "Value"],
    )
    mgr.update_context(
        cid,
        countries=["India"],
        metrics=["GDP"],
        append_countries=False,
        append_metrics=False,
        question="Analyze India's GDP",
        resolved_question="Analyze India's GDP",
        operation="analyze",
        intent="eda",
    )
    mgr.record_filter(cid, column="Year", operator="gt", value=2010, label="Year > 2010")
    mgr.record_visualization(
        cid, chart_type="line", columns=["Year", "Value"], title="GDP after 2010"
    )
    mgr.record_analysis(
        cid,
        question="Show GDP after 2010",
        resolved_question="Show GDP after 2010",
        operation="filter_visualize",
        summary="Filtered GDP after 2010",
        countries=["India"],
        metrics=["GDP"],
    )


def test_resolve_it_to_india_gdp():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Compare it with China.")
    assert isinstance(result, ResolvedRequest)
    assert result.is_follow_up is True
    assert result.reuse_active_dataset is True
    assert "India GDP" in result.resolved_question
    assert "China" in result.resolved_question
    assert result.primary_topic == "India GDP"
    assert any(r.kind in {ReferenceKind.IT, ReferenceKind.THAT} or "it" in r.original_span.lower()
               for r in result.resolved_references) or "India GDP" in result.resolved_question


def test_resolve_same_dataset():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Forecast the same dataset for next 5 years")
    assert "India GDP" in result.resolved_question
    assert result.reuse_active_dataset is True


def test_resolve_previous_chart():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Explain the previous chart")
    assert result.is_follow_up is True
    assert any(r.kind == ReferenceKind.PREVIOUS_CHART for r in result.resolved_references)
    assert result.last_chart is not None
    assert result.last_chart.chart_type == "line"


def test_resolve_that_country():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Show inflation for that country")
    assert "India" in result.resolved_question
    assert any(r.kind == ReferenceKind.THAT_COUNTRY for r in result.resolved_references)


def test_resolve_same_filter():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Apply same filter to population")
    assert "Year > 2010" in result.resolved_question
    assert result.filters
    assert result.filters[0].column == "Year"


def test_resolve_last_analysis():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Summarize last analysis")
    assert result.is_follow_up is True
    assert any(r.kind == ReferenceKind.LAST_ANALYSIS for r in result.resolved_references)
    assert result.last_analysis is not None


def test_resolve_forecast_follow_up_remembers_filter():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Forecast the next 5 years.")
    # May or may not rewrite if no pronoun — still attach context
    assert result.dataset_refs
    assert result.filters
    assert any(f.label == "Year > 2010" for f in result.filters)
    assert result.primary_topic == "India GDP"


def test_resolve_without_context():
    mgr = ConversationContextManager()
    result = mgr.resolve_reference("missing", "Analyze GDP", allow_missing_context=True)
    assert result.resolved_question == "Analyze GDP"
    assert result.is_follow_up is False


def test_resolve_module_level():
    save_context(
        "ml",
        {
            "active_datasets": [{"topic": "Gold Price", "is_active": True}],
            "metrics": ["Gold Price"],
            "selected_countries": [],
        },
    )
    result = resolve_reference("ml", "Plot it")
    assert "Gold Price" in result.resolved_question


def test_resolved_request_to_dict():
    mgr = ConversationContextManager()
    _seed_india_gdp(mgr)
    result = mgr.resolve_reference("conv1", "Compare it with China")
    d = result.to_dict()
    assert d["original_question"]
    assert d["resolved_question"]
    assert "dataset_refs" in d
    assert "filters" in d
    # Round-trip
    back = ResolvedRequest.from_dict(d)
    assert back.primary_topic == result.primary_topic


def test_multi_conversation_isolation():
    mgr = ConversationContextManager()
    mgr.record_dataset("A", topic="India GDP", local_path="/a.csv")
    mgr.record_dataset("B", topic="China Population", local_path="/b.csv")
    ra = mgr.resolve_reference("A", "Forecast it")
    rb = mgr.resolve_reference("B", "Forecast it")
    assert "India GDP" in ra.resolved_question
    assert "China Population" in rb.resolved_question


def test_ttl_configurable_purge():
    store = ConversationMemoryStore(ttl_seconds=1)
    mgr = ConversationContextManager(store=store, ttl_seconds=1)
    mgr.save_context("t1", ConversationContext(conversation_id="t1", metrics=["X"]))
    # Manually age
    ctx = store._store["t1"]
    old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    ctx.last_activity_at = old
    ctx.updated_at = old
    n = mgr.purge_expired()
    assert n >= 1
    assert mgr.has_context("t1") is False
