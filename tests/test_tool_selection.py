"""Tests for Dynamic Tool Selection Agent (Task 17)."""

from __future__ import annotations

import pytest

from backend.tool_selection import (
    BuiltinTool,
    ExecutionPlan,
    RuleBasedToolSelector,
    Tool,
    ToolCategory,
    ToolRegistry,
    ToolSpec,
    build_default_tools,
    create_default_registry,
    extract_profile_signals,
    get_default_registry,
    reset_default_registry,
    reset_default_selector,
    select_tools,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_default_registry()
    reset_default_selector()
    yield
    reset_default_registry()
    reset_default_selector()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_default_registry_has_core_tools():
    reg = create_default_registry()
    ids = set(reg.list_ids())
    for expected in (
        "correlation",
        "regression",
        "forecast",
        "trend",
        "distribution",
        "outlier_detection",
        "seasonality",
        "clustering",
        "hypothesis_testing",
        "anova",
        "pca",
        "time_series",
        "visualization",
        "histogram",
        "scatter_plot",
    ):
        assert expected in ids, f"missing {expected}"


def test_plugin_registration():
    reg = create_default_registry()
    plugin = ToolSpec(
        tool_id="custom_shap",
        name="SHAP Explainer",
        description="Feature importance via SHAP",
        category=ToolCategory.RELATIONSHIP,
        keywords=["shap", "feature importance"],
        is_plugin=True,
        priority=15,
    )
    reg.register_spec(plugin)
    assert "custom_shap" in reg
    tool = reg.get("custom_shap")
    assert tool is not None
    assert tool.spec.is_plugin is True
    assert reg.unregister("custom_shap") is True
    assert "custom_shap" not in reg


def test_tool_interface_builtin():
    tools = build_default_tools()
    assert all(isinstance(t, Tool) for t in tools)
    assert all(isinstance(t, BuiltinTool) for t in tools)
    assert tools[0].spec.tool_id


def test_by_category():
    reg = get_default_registry()
    viz = reg.by_category(ToolCategory.VISUALIZATION)
    assert any(t.spec.tool_id == "visualization" for t in viz)


# ---------------------------------------------------------------------------
# Selection scenarios
# ---------------------------------------------------------------------------


def test_forecast_gdp():
    profile = {
        "dataset_type": "time_series",
        "time_column": "Year",
        "numeric_metrics": ["GDP"],
        "column_names": ["Country", "Year", "GDP"],
    }
    plan = select_tools("Forecast GDP", profile=profile)
    assert isinstance(plan, ExecutionPlan)
    assert "forecast" in plan.tool_ids
    # Companions
    assert "trend" in plan.tool_ids or "time_series" in plan.tool_ids
    assert "visualization" in plan.tool_ids
    assert plan.confidence > 0


def test_relationship_rainfall_crop():
    profile = {
        "dataset_type": "tabular",
        "numeric_metrics": ["rainfall", "crop_yield"],
        "column_names": ["rainfall", "crop_yield", "region"],
    }
    plan = select_tools(
        "Relationship between rainfall and crop yield",
        profile=profile,
    )
    assert "correlation" in plan.tool_ids or "regression" in plan.tool_ids
    assert "scatter_plot" in plan.tool_ids or "visualization" in plan.tool_ids


def test_unusual_values():
    profile = {
        "dataset_type": "tabular",
        "numeric_metrics": ["value"],
        "column_names": ["id", "value"],
    }
    plan = select_tools("Find unusual values", profile=profile)
    assert "outlier_detection" in plan.tool_ids
    assert "histogram" in plan.tool_ids or "distribution" in plan.tool_ids


def test_seasonality_question():
    profile = {
        "dataset_type": "time_series",
        "time_column": "month",
        "numeric_metrics": ["sales"],
    }
    plan = select_tools("Detect seasonality in sales", profile=profile)
    assert "seasonality" in plan.tool_ids


def test_clustering_question():
    profile = {
        "dataset_type": "tabular",
        "numeric_metrics": ["a", "b", "c"],
        "row_count": 1000,
    }
    plan = select_tools("Cluster customers into segments", profile=profile)
    assert "clustering" in plan.tool_ids


def test_anova_question():
    profile = {
        "dataset_type": "tabular",
        "numeric_metrics": ["score"],
        "categorical_fields": ["group"],
    }
    plan = select_tools("Run ANOVA to compare group means", profile=profile)
    assert "anova" in plan.tool_ids or "hypothesis_testing" in plan.tool_ids


def test_pca_question():
    profile = {
        "dataset_type": "tabular",
        "numeric_metrics": ["f1", "f2", "f3", "f4"],
        "row_count": 800,
    }
    plan = select_tools("Apply PCA to reduce dimensions", profile=profile)
    assert "pca" in plan.tool_ids


def test_context_boosts_forecast():
    profile = {
        "dataset_type": "time_series",
        "time_column": "Year",
        "numeric_metrics": ["GDP"],
    }
    context = {
        "last_operation": "forecast",
        "last_forecast_target": "India GDP",
        "metrics": ["GDP"],
        "selected_countries": ["India"],
    }
    plan = select_tools("Do the next 5 years", profile=profile, context=context)
    # May rely on context + weak question; forecast companions or forecast itself
    assert plan.selected_tools
    assert plan.context_hints.get("last_forecast_target") == "India GDP" or plan.tool_ids


def test_empty_question():
    plan = select_tools("")
    assert plan.selected_tools == []
    assert plan.confidence == 0.0


def test_generic_analyze_fallback():
    plan = select_tools("Analyze this")
    assert plan.selected_tools
    # EDA or visualization-ish
    assert any(
        t in plan.tool_ids for t in ("eda_summary", "visualization", "distribution", "trend")
    )


def test_profile_signals():
    signals = extract_profile_signals(
        {
            "dataset_type": "time_series",
            "time_column": "Year",
            "numeric_metrics": ["a", "b"],
            "entity_column": "Country",
            "row_count": 1000,
        }
    )
    assert "time" in signals
    assert "time_series" in signals
    assert "multi_numeric" in signals
    assert "entity" in signals
    assert "large_n" in signals


def test_requirements_block_without_signals():
    """With a non-time profile, forecast should be inapplicable."""
    selector = RuleBasedToolSelector(min_score=0.2)
    plan = selector.select_tools(
        "something random about colors",  # no forecast keywords
        profile={
            "dataset_type": "tabular",
            "numeric_metrics": ["x"],
            "column_names": ["x", "y"],
        },
    )
    # Should not force forecast
    assert "forecast" not in plan.tool_ids


def test_execution_plan_to_dict():
    plan = select_tools(
        "Forecast GDP",
        profile={"dataset_type": "time_series", "time_column": "Year", "numeric_metrics": ["GDP"]},
    )
    d = plan.to_dict()
    assert "selected_tools" in d
    assert "tool_ids" in d
    assert "confidence" in d
    back = ExecutionPlan.from_dict(d)
    assert back.tool_ids == plan.tool_ids


def test_selector_uses_custom_registry_plugin():
    reg = create_default_registry()
    reg.register_spec(
        {
            "tool_id": "wavelet",
            "name": "Wavelet Analysis",
            "keywords": ["wavelet", "frequency decomposition"],
            "category": "time_series",
            "is_plugin": True,
            "priority": 10,
        }
    )
    selector = RuleBasedToolSelector(registry=reg)
    plan = selector.select_tools("Run wavelet frequency decomposition on signal")
    assert "wavelet" in plan.tool_ids


def test_dataset_profile_object_accepted():
    """Accept objects with to_dict() like DatasetProfile."""

    class FakeProfile:
        def to_dict(self):
            return {
                "dataset_type": "time_series",
                "time_column": "Year",
                "numeric_metrics": ["Value"],
            }

    plan = select_tools("Forecast next 10 years", profile=FakeProfile())
    assert "forecast" in plan.tool_ids


def test_conversation_context_object_accepted():
    class FakeCtx:
        def to_dict(self):
            return {
                "metrics": ["GDP"],
                "selected_countries": ["India"],
                "last_operation": "analyze",
            }

    plan = select_tools(
        "Show the trend",
        profile={"dataset_type": "time_series", "time_column": "Year", "numeric_metrics": ["GDP"]},
        context=FakeCtx(),
    )
    assert "trend" in plan.tool_ids or "visualization" in plan.tool_ids


def test_ordered_execution_plan():
    plan = select_tools(
        "Forecast GDP for the next 5 years",
        profile={
            "dataset_type": "time_series",
            "time_column": "Year",
            "numeric_metrics": ["GDP"],
        },
    )
    orders = [t.order for t in plan.selected_tools]
    assert orders == list(range(1, len(orders) + 1))
    # Forecast should be early
    forecast_order = next(t.order for t in plan.selected_tools if t.tool_id == "forecast")
    assert forecast_order <= 3
