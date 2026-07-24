"""Tests for multi-dataset planning (no execution)."""

from backend.planning import (
    MultiDatasetIntent,
    MultiDatasetPlanner,
    plan_dataset_requests,
    plan_multi_dataset,
)
from backend.retrieval.models import DatasetRequest


def test_compare_multiple_metrics():
    q = "Compare India GDP, Population, Inflation and CO2 emissions"
    plan = plan_multi_dataset(q)
    assert plan.is_multi is True
    assert plan.intent == MultiDatasetIntent.COMPARISON
    assert "India" in plan.entities
    topics = [t.lower() for t in plan.topics()]
    assert len(plan.requests) >= 4
    assert any("gdp" in t for t in topics)
    assert any("population" in t for t in topics)
    assert any("inflation" in t for t in topics)
    assert any("co2" in t or "emission" in t for t in topics)
    assert all(isinstance(r, DatasetRequest) for r in plan.requests)


def test_correlation_request():
    plan = plan_multi_dataset("Show correlation between GDP and inflation")
    assert plan.intent == MultiDatasetIntent.CORRELATION
    assert plan.is_multi is True
    topics = [t.lower() for t in plan.topics()]
    assert any("gdp" in t for t in topics)
    assert any("inflation" in t for t in topics)


def test_forecast_single_metric_preserved():
    plan = plan_multi_dataset("Forecast India GDP for next 5 years")
    assert plan.intent == MultiDatasetIntent.FORECASTING
    # Single metric → not multi
    assert len(plan.requests) == 1
    assert plan.is_multi is False
    assert "gdp" in plan.requests[0].topic.lower()


def test_single_dataset_behavior_preserved():
    reqs = plan_dataset_requests("Analyze India GDP")
    assert len(reqs) == 1
    assert isinstance(reqs[0], DatasetRequest)
    assert "gdp" in reqs[0].topic.lower()


def test_multi_metric_without_compare_keyword():
    plan = MultiDatasetPlanner().plan(
        "Analyze GDP population inflation for India"
    )
    assert len(plan.requests) >= 3
    assert plan.is_multi is True


def test_empty_question():
    plan = plan_multi_dataset("")
    assert plan.requests == []
