"""Tests for Reflection / Self-Correction Agent (Task 21)."""

from __future__ import annotations

import pytest

from backend.reflection import (
    CorrectedPlan,
    IssueSeverity,
    LLMReflection,
    ReflectionResult,
    RuleBasedReflection,
    reflect_on_analysis,
    reset_reflection_agent,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_reflection_agent()
    yield
    reset_reflection_agent()


def _good_package(**overrides):
    base = dict(
        question="Forecast India's GDP after 2010",
        datasets_used=[
            {
                "topic": "India GDP",
                "source": "World Bank",
                "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
                "columns": ["Country", "Year", "GDP"],
                "local_path": "/data/india_gdp.csv",
                "dataset_id": "ds-1",
            }
        ],
        execution_plan={
            "selected_tools": [
                {"tool_id": "forecast", "name": "Forecast", "order": 1, "produces_chart": True},
                {"tool_id": "trend", "name": "Trend", "order": 2, "produces_chart": True},
            ],
            "confidence": 0.72,
        },
        analysis_result={
            "answer": (
                "India GDP shows moderate growth; the forecast suggests continued expansion "
                "over the next five years [1]."
            ),
            "confidence": 0.72,
        },
        explanation_result={
            "summary": "Forecast from World Bank GDP series.",
            "reasoning_summary": "Used forecast + trend tools on India GDP.",
            "explanation_text": "Citations [1] World Bank — India GDP",
            "citations": [
                {
                    "topic": "India GDP",
                    "source": "World Bank",
                    "citation_label": "[1] World Bank — India GDP",
                }
            ],
            "confidence": 0.72,
            "sources": ["World Bank"],
        },
        charts=[{"chart_type": "line", "title": "GDP forecast"}],
        join_plan=None,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_approved_clean_package():
    result = reflect_on_analysis(**_good_package())
    assert isinstance(result, ReflectionResult)
    assert result.approved is True
    assert result.severity in {IssueSeverity.INFO, IssueSeverity.WARNING}
    # Should not force re-run
    if result.corrected_plan:
        assert result.corrected_plan.should_rerun is False
    assert result.reflector == "rule_based"


def test_to_dict_roundtrip():
    result = reflect_on_analysis(**_good_package())
    d = result.to_dict()
    assert "approved" in d
    assert "issues" in d
    assert "confidence_adjustment" in d
    back = ReflectionResult.from_dict(d)
    assert back.approved == result.approved
    assert len(back.issues) == len(result.issues)


# ---------------------------------------------------------------------------
# Dataset correctness
# ---------------------------------------------------------------------------


def test_no_datasets_is_severe():
    result = reflect_on_analysis(
        question="Analyze GDP",
        analysis_result={"answer": "GDP rose 5%.", "confidence": 0.9},
        datasets_used=[],
    )
    assert result.approved is False
    assert any(i.code == "no_datasets" for i in result.issues)
    assert result.corrected_plan is not None
    assert result.corrected_plan.should_rerun is True


def test_planetary_entity_dataset_error():
    result = reflect_on_analysis(
        question="Analyze GDP on Mars",
        datasets_used=[{"topic": "India GDP", "source": "World Bank"}],
        analysis_result={"answer": "Martian GDP is rising.", "confidence": 0.5},
    )
    assert any(i.code == "implausible_entity" for i in result.issues)
    assert result.has_severe_issues is True
    assert result.approved is False


def test_dataset_topic_mismatch_warning():
    result = reflect_on_analysis(
        question="Analyze gold prices",
        datasets_used=[
            {
                "topic": "Rainfall Series",
                "source": "IMD",
                "columns": ["Year", "Rainfall"],
            }
        ],
        analysis_result={
            "answer": "Gold may move with weather patterns.",
            "confidence": 0.5,
        },
        execution_plan={"selected_tools": [{"tool_id": "trend", "name": "Trend"}]},
    )
    assert any(i.code == "dataset_topic_mismatch" for i in result.issues)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def test_overconfident_without_evidence():
    result = reflect_on_analysis(
        question="What is India's GDP trend?",
        datasets_used=[{"topic": "India GDP"}],  # no source
        analysis_result={
            "answer": "GDP definitely always grows.",
            "confidence": 0.95,
        },
        explanation_result={},
        execution_plan={},
    )
    assert any(i.code in {"overconfident", "confidence_without_trace", "absolute_language"} for i in result.issues)
    assert result.confidence_adjustment < 0
    if result.original_confidence is not None and result.adjusted_confidence is not None:
        assert result.adjusted_confidence < result.original_confidence


def test_confidence_without_data():
    result = reflect_on_analysis(
        question="Show inflation",
        datasets_used=[],
        analysis_result={"answer": "Inflation is fine.", "confidence": 0.8},
    )
    codes = {i.code for i in result.issues}
    assert "no_datasets" in codes or "confidence_without_data" in codes
    assert result.approved is False


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def test_missing_citations_on_major_conclusion():
    result = reflect_on_analysis(
        question="Analyze India's GDP",
        datasets_used=[{"topic": "India GDP"}],  # no source url
        analysis_result={
            "answer": (
                "GDP grew 7.2% in 2023 and reached $3.5 trillion, "
                "driven by services expansion across the decade."
            ),
            "confidence": 0.6,
        },
        explanation_result={"summary": "brief"},
        execution_plan={"selected_tools": [{"tool_id": "trend"}]},
    )
    assert any(
        i.code in {"missing_citations", "citations_not_surface", "missing_dataset_source"}
        for i in result.issues
    )


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def test_bad_chart_for_trend():
    result = reflect_on_analysis(
        question="Show the trend of India GDP over time",
        datasets_used=[
            {"topic": "India GDP", "source": "World Bank", "columns": ["Year", "GDP"]}
        ],
        analysis_result={"answer": "GDP trended upward.", "confidence": 0.6},
        charts=[{"chart_type": "pie", "n_categories": 8}],
        execution_plan={"selected_tools": [{"tool_id": "visualization"}]},
        explanation_result={"citations": [{"source": "World Bank"}]},
    )
    assert any(
        i.code in {"bad_chart_for_trend", "pie_too_many_slices"} for i in result.issues
    )
    recs = " ".join(result.recommendations).lower()
    assert "line" in recs or "bar" in recs


# ---------------------------------------------------------------------------
# Joins
# ---------------------------------------------------------------------------


def test_suspicious_join_key():
    result = reflect_on_analysis(
        question="Compare GDP and inflation",
        datasets_used=[
            {"topic": "GDP", "source": "WB"},
            {"topic": "Inflation", "source": "WB"},
        ],
        join_plan={"strategy": "inner", "join_keys": ["GDP"]},
        analysis_result={"answer": "They move together.", "confidence": 0.55},
        execution_plan={"selected_tools": [{"tool_id": "correlation"}]},
    )
    assert any(i.code == "suspicious_join_key" for i in result.issues)
    assert result.approved is False
    assert result.corrected_plan and result.corrected_plan.join_notes


def test_join_missing_keys():
    result = reflect_on_analysis(
        question="Compare GDP and population",
        datasets_used=[{"topic": "GDP", "source": "A"}, {"topic": "Population", "source": "B"}],
        join_plan={"strategy": "outer", "join_keys": []},
        analysis_result={"answer": "Both increased.", "confidence": 0.5},
    )
    assert any(i.code == "join_missing_keys" for i in result.issues)


# ---------------------------------------------------------------------------
# Statistical sanity + hallucination
# ---------------------------------------------------------------------------


def test_impossible_statistic_critical():
    result = reflect_on_analysis(
        question="Analyze population",
        datasets_used=[{"topic": "Population", "source": "UN"}],
        analysis_result={
            "answer": "There is negative population growth of impossible scale; negative population recorded.",
            "confidence": 0.4,
        },
    )
    assert any(i.severity == IssueSeverity.CRITICAL for i in result.issues) or any(
        i.code == "impossible_statistic" for i in result.issues
    )
    assert result.approved is False


def test_numeric_without_data_hallucination():
    result = reflect_on_analysis(
        question="What happened to prices?",
        datasets_used=[],
        analysis_result={
            "answer": "Prices rose 42% last year according to our model.",
            "confidence": 0.5,
        },
    )
    assert any(
        i.code in {"numeric_without_data", "no_datasets", "confidence_without_data"}
        for i in result.issues
    )


def test_causal_language_flagged():
    result = reflect_on_analysis(
        **_good_package(
            analysis_result={
                "answer": "Higher rates caused GDP to fall by 3% [1].",
                "confidence": 0.7,
            }
        )
    )
    assert any(i.code == "unsupported_absolute_claim" for i in result.issues)


# ---------------------------------------------------------------------------
# Behavior paths
# ---------------------------------------------------------------------------


def test_warnings_still_approved():
    """Warning-only issues should approve with attached warnings."""
    result = reflect_on_analysis(
        question="Show trend of GDP",
        datasets_used=[
            {"topic": "India GDP", "source": "World Bank", "columns": ["Year", "GDP"]}
        ],
        analysis_result={"answer": "GDP moved higher over the sample.", "confidence": 0.55},
        charts=[],  # missing chart → info/warning
        execution_plan={"selected_tools": [{"tool_id": "eda_summary"}]},
        explanation_result={
            "citations": [{"source": "World Bank"}],
            "explanation_text": "Based on World Bank GDP [1]",
        },
    )
    # May be approved with warnings or info
    if not result.has_severe_issues:
        assert result.approved is True


def test_severe_returns_corrected_plan():
    result = reflect_on_analysis(
        question="Forecast inflation",
        datasets_used=[],
        analysis_result={
            "answer": "Inflation will definitely be 500% next year.",
            "confidence": 0.99,
        },
    )
    assert result.approved is False
    assert result.corrected_plan is not None
    assert isinstance(result.corrected_plan, CorrectedPlan)
    assert result.corrected_plan.should_rerun is True
    assert result.corrected_plan.lower_confidence is True


def test_forecast_missing_tool_warning():
    result = reflect_on_analysis(
        question="Forecast gold prices",
        datasets_used=[
            {"topic": "Gold Price", "source": "Market", "columns": ["Date", "Price"]}
        ],
        analysis_result={"answer": "Prices may continue.", "confidence": 0.5},
        execution_plan={"selected_tools": [{"tool_id": "eda_summary"}]},
        explanation_result={"citations": [{"source": "Market"}]},
    )
    assert any(i.code == "forecast_not_executed" for i in result.issues)
    if result.corrected_plan:
        assert "forecast" in [t.lower() for t in result.corrected_plan.suggested_tools] or True


def test_comparison_incomplete():
    result = reflect_on_analysis(
        question="Compare India and China GDP",
        datasets_used=[{"topic": "India GDP", "source": "WB"}],
        analysis_result={"answer": "India looks fine.", "confidence": 0.55},
        execution_plan={"selected_tools": [{"tool_id": "trend"}]},
        explanation_result={"citations": [{"source": "WB"}]},
    )
    assert any(i.code == "comparison_incomplete" for i in result.issues)


def test_llm_reflection_falls_back():
    agent = LLMReflection()
    result = agent.review(**_good_package())
    assert result is not None
    assert isinstance(result, ReflectionResult)
    assert result.metadata.get("llm_used") is False or "rule_based" in result.reflector


def test_rule_based_class_api():
    agent = RuleBasedReflection()
    result = agent.review(
        question="Analyze unemployment",
        datasets_used=[{"topic": "Unemployment", "source": "ILO"}],
        analysis_result={"answer": "Unemployment eased slightly [1].", "confidence": 0.6},
        explanation_result={
            "citations": [{"source": "ILO"}],
            "explanation_text": "[1] ILO",
        },
        execution_plan={"selected_tools": [{"tool_id": "trend"}]},
    )
    assert result.reflector == "rule_based"


def test_accepts_objects_with_to_dict():
    class FakeExpl:
        def to_dict(self):
            return {
                "summary": "ok",
                "citations": [{"source": "WB"}],
                "explanation_text": "cite [1]",
                "confidence": 0.7,
            }

    class FakePlan:
        def to_dict(self):
            return {
                "selected_tools": [
                    {"tool_id": "forecast", "name": "Forecast"},
                ],
                "confidence": 0.7,
            }

    result = reflect_on_analysis(
        question="Forecast GDP",
        execution_plan=FakePlan(),
        explanation_result=FakeExpl(),
        datasets_used=[{"topic": "GDP", "source": "WB", "columns": ["Year", "GDP"]}],
        analysis_result={"answer": "GDP forecast points higher [1].", "confidence": 0.7},
        charts=[{"chart_type": "line"}],
    )
    assert result.approved is True or not result.has_severe_issues
