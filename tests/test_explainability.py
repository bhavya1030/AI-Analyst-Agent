"""Tests for Explainability Layer (Task 19)."""

from __future__ import annotations

import pytest

from backend.explainability import (
    ExplanationResult,
    ExplanationStyle,
    LLMExplainer,
    RuleBasedExplainer,
    generate_explanation,
    reset_default_explainer,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_default_explainer()
    yield
    reset_default_explainer()


def _sample_inputs():
    datasets = [
        {
            "topic": "India GDP",
            "dataset_id": "ds-gdp-1",
            "source": "World Bank",
            "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
            "provider": "world_bank",
            "columns": ["Country", "Year", "Value"],
            "row_count": 50,
            "local_path": "/data/india_gdp.csv",
        },
        {
            "topic": "India Inflation",
            "dataset_id": "ds-inf-1",
            "source": "World Bank",
            "download_url": "https://data.worldbank.org/indicator/FP.CPI.TOTL",
            "columns": ["Country", "Year", "CPI"],
            "row_count": 50,
        },
    ]
    execution_plan = {
        "question": "Forecast India GDP",
        "selected_tools": [
            {
                "tool_id": "forecast",
                "name": "Forecast",
                "category": "predictive",
                "score": 0.9,
                "reason": "Forecast keywords",
                "order": 1,
                "produces_chart": True,
            },
            {
                "tool_id": "trend",
                "name": "Trend",
                "category": "time_series",
                "order": 2,
                "produces_chart": True,
            },
            {
                "tool_id": "visualization",
                "name": "Visualization",
                "order": 3,
                "produces_chart": True,
            },
        ],
        "tool_ids": ["forecast", "trend", "visualization"],
        "confidence": 0.82,
        "warnings": ["Sample warning from plan"],
    }
    join_plan = {
        "strategy": "outer",
        "join_keys": ["Country", "Year"],
        "datasets_merged": 2,
        "warnings": ["Auto-selected merge strategy: outer"],
        "schema_alignment": {
            "join_keys": ["Country", "Year"],
            "rename_maps": [{"Country Name": "Country"}, {"Nation": "Country"}],
        },
    }
    analysis_result = {
        "answer": "GDP is projected to grow modestly over the next 5 years.",
        "insights": [{"summary": "Upward trend with recent slowdown"}],
        "confidence": 0.75,
        "columns_used": ["Year", "Value", "CPI"],
    }
    filters = [
        {"column": "Year", "operator": "gt", "value": 2010, "label": "Year > 2010"},
        {"column": "Country", "operator": "eq", "value": "India", "label": "Country = India"},
    ]
    return {
        "question": "Forecast India GDP after 2010",
        "datasets_used": datasets,
        "execution_plan": execution_plan,
        "join_plan": join_plan,
        "analysis_result": analysis_result,
        "filters": filters,
        "columns_used": ["Year", "Value"],
    }


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def test_generate_explanation_detailed():
    result = generate_explanation(**_sample_inputs(), style=ExplanationStyle.DETAILED)
    assert isinstance(result, ExplanationResult)
    assert result.explainer == "rule_based"
    assert result.style == ExplanationStyle.DETAILED
    assert result.explanation_text
    assert "Datasets used" in result.detailed_text or "dataset" in result.detailed_text.lower()
    assert result.reasoning_summary
    assert result.confidence > 0
    assert len(result.datasets_used) == 2
    assert "World Bank" in result.sources or any("World Bank" in s for s in result.sources)


def test_short_detailed_technical_styles():
    base = _sample_inputs()
    short = generate_explanation(**base, style="short")
    detailed = generate_explanation(**base, style="detailed")
    technical = generate_explanation(**base, style="technical")

    assert short.style == ExplanationStyle.SHORT
    assert detailed.style == ExplanationStyle.DETAILED
    assert technical.style == ExplanationStyle.TECHNICAL

    assert short.explanation_text == short.short_text
    assert detailed.explanation_text == detailed.detailed_text
    assert technical.explanation_text == technical.technical_text

    assert len(short.short_text) < len(detailed.detailed_text)
    assert "confidence:" in technical.technical_text.lower()
    assert "tools" in technical.technical_text.lower()


def test_datasets_sources_columns_filters_joins_tools():
    result = generate_explanation(**_sample_inputs())
    assert any(d.topic == "India GDP" for d in result.datasets_used)
    assert any(d.topic == "India Inflation" for d in result.datasets_used)
    assert result.sources
    assert "Year" in result.columns_used or "Value" in result.columns_used
    assert len(result.filters_applied) == 2
    assert any("2010" in (f.label or "") for f in result.filters_applied)
    assert result.joins_performed is not None
    assert result.joins_performed.strategy == "outer"
    assert "Country" in result.joins_performed.join_keys
    assert "Year" in result.joins_performed.join_keys
    tool_ids = [t.tool_id for t in result.tools_executed]
    assert "forecast" in tool_ids
    assert "trend" in tool_ids


def test_citations():
    result = generate_explanation(**_sample_inputs())
    assert result.citations
    assert any(c.dataset_id == "ds-gdp-1" for c in result.citations)
    assert any("World Bank" in (c.citation_label or c.source or "") for c in result.citations)
    assert "Citations" in result.detailed_text or "[" in result.detailed_text


def test_warnings_and_limitations():
    result = generate_explanation(**_sample_inputs())
    assert any("Sample warning" in w for w in result.warnings)
    assert result.limitations
    assert any("causation" in lim.lower() for lim in result.limitations)


def test_reasoning_includes_pipeline_steps():
    result = generate_explanation(**_sample_inputs())
    r = result.reasoning_summary.lower()
    assert "dataset" in r
    assert "forecast" in r or "analytical" in r
    assert "outer" in r or "join" in r or "combined" in r


# ---------------------------------------------------------------------------
# Flexible inputs / edge cases
# ---------------------------------------------------------------------------


def test_from_execution_result_shape():
    """Accept ExecutionResult-like dict without separate datasets_used."""
    result = generate_explanation(
        question="Compare GDP and population",
        analysis_result={
            "answer": "Both series rose.",
            "datasets_processed": [
                {
                    "topic": "GDP",
                    "local_path": "/g.csv",
                    "dataset_id": "1",
                    "profile": {"column_names": ["Country", "Year", "GDP"], "row_count": 10},
                },
                {
                    "topic": "Population",
                    "local_path": "/p.csv",
                    "dataset_id": "2",
                    "columns": ["Country", "Year", "Population"],
                },
            ],
            "join_strategy": "outer",
            "join_keys": ["Country", "Year"],
            "topics_succeeded": ["GDP", "Population"],
            "warnings": [],
        },
        execution_plan={
            "selected_tools": [
                {"tool_id": "comparison", "name": "Comparison", "order": 1},
                {"tool_id": "visualization", "name": "Visualization", "order": 2},
            ],
            "confidence": 0.7,
        },
    )
    assert len(result.datasets_used) >= 2
    assert result.joins_performed is not None
    assert result.joins_performed.strategy == "outer"
    assert any(t.tool_id == "comparison" for t in result.tools_executed)


def test_object_with_to_dict():
    class FakePlan:
        def to_dict(self):
            return {
                "selected_tools": [{"tool_id": "pca", "name": "PCA", "order": 1}],
                "confidence": 0.6,
            }

    class FakeDataset:
        def to_dict(self):
            return {
                "topic": "Features",
                "source": "Internal",
                "columns": ["f1", "f2", "f3"],
            }

    result = generate_explanation(
        question="Apply PCA",
        execution_plan=FakePlan(),
        datasets_used=[FakeDataset()],
        style="short",
    )
    assert any(t.tool_id == "pca" for t in result.tools_executed)
    assert result.datasets_used[0].topic == "Features"


def test_minimal_inputs():
    result = generate_explanation(question="Hello")
    assert isinstance(result, ExplanationResult)
    assert result.explanation_text
    assert result.confidence >= 0
    assert result.limitations  # still has generic limitations


def test_empty_everything():
    result = generate_explanation()
    assert result.summary
    assert result.short_text
    assert result.detailed_text
    assert result.technical_text


def test_explicit_confidence_override():
    result = generate_explanation(
        question="x",
        confidence=0.91,
        datasets_used=[{"topic": "T", "source": "S"}],
    )
    assert result.confidence == 0.91


def test_to_dict_roundtrip():
    result = generate_explanation(**_sample_inputs())
    d = result.to_dict()
    assert "datasets_used" in d
    assert "tools_executed" in d
    assert "reasoning_summary" in d
    assert "citations" in d
    back = ExplanationResult.from_dict(d)
    assert back.question == result.question
    assert len(back.datasets_used) == len(result.datasets_used)
    assert back.confidence == result.confidence


def test_rule_based_class_api():
    explainer = RuleBasedExplainer()
    result = explainer.generate_explanation(
        question="Find outliers",
        execution_plan={
            "tool_ids": ["outlier_detection", "histogram"],
            "selected_tools": [
                {"tool_id": "outlier_detection", "name": "Outlier Detection", "order": 1},
                {"tool_id": "histogram", "name": "Histogram", "order": 2},
            ],
        },
        datasets_used=[{"topic": "Sales", "source": "CSV Upload"}],
        style=ExplanationStyle.SHORT,
    )
    assert result.style == ExplanationStyle.SHORT
    assert "outlier" in result.explanation_text.lower() or "Outlier" in result.tools_executed[0].name


def test_llm_explainer_falls_back_without_llm():
    explainer = LLMExplainer()
    result = explainer.generate_explanation(**_sample_inputs())
    assert result.datasets_used
    # Without USE_LLM flags, should not claim pure llm
    assert result.metadata.get("llm_used") is False or "rule_based" in result.explainer


def test_all_required_sections_present_in_detailed():
    text = generate_explanation(**_sample_inputs(), style="detailed").detailed_text.lower()
    for needle in (
        "dataset",
        "source",
        "column",
        "filter",
        "join",
        "tool",
        "confidence",
        "warning",
        "limitation",
    ):
        assert needle in text, f"missing section about {needle}"
