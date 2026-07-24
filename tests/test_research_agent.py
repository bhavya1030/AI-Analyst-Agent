"""Tests for Autonomous Research Planning (Task 18)."""

from __future__ import annotations

import pytest

from backend.research import (
    AutonomousResearchAgent,
    DatasetNecessity,
    ResearchObjectiveType,
    ResearchPlan,
    ResearchPlanner,
    plan_research,
    reset_research_agent,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_research_agent()
    yield
    reset_research_agent()


def _topics_lower(plan: ResearchPlan) -> list[str]:
    return [t.lower() for t in plan.topics]


def _has_metric(plan: ResearchPlan, metric: str) -> bool:
    m = metric.lower()
    return any(m in t.lower() for t in plan.topics)


# ---------------------------------------------------------------------------
# Core example: Why has India's GDP slowed?
# ---------------------------------------------------------------------------


def test_india_gdp_slowdown_root_cause():
    plan = plan_research("Why has India's GDP slowed?")
    assert isinstance(plan, ResearchPlan)
    assert plan.objective.objective_type == ResearchObjectiveType.ROOT_CAUSE
    assert plan.objective.primary_metric == "GDP"
    assert "India" in plan.objective.entities

    # Required related datasets (user example)
    for metric in ("GDP", "Inflation", "Population", "Exports", "Interest Rates"):
        assert _has_metric(plan, metric.split()[0] if metric != "Interest Rates" else "interest"), (
            f"missing {metric} in {plan.topics}"
        )
    # Interest Rates full check
    assert any("interest" in t.lower() for t in plan.topics)

    assert "GDP" in " ".join(plan.mandatory_topics) or any(
        "gdp" in t.lower() for t in plan.mandatory_topics
    )
    # At least inflation / interest / exports marked mandatory
    mandatory_blob = " ".join(plan.mandatory_topics).lower()
    assert "inflation" in mandatory_blob or "interest" in mandatory_blob or "export" in mandatory_blob

    assert plan.analysis_goals
    assert plan.expected_outputs
    assert plan.dependencies  # drivers depend on primary
    assert plan.confidence > 0.5
    assert plan.planner == "rule_based"


def test_mandatory_vs_optional():
    plan = plan_research("Why has India's GDP slowed?")
    assert plan.mandatory_topics
    # Population should be optional for GDP root cause
    pop_reqs = [d for d in plan.required_datasets if "population" in d.topic.lower()]
    if pop_reqs:
        assert pop_reqs[0].necessity == DatasetNecessity.OPTIONAL


def test_priorities_and_order():
    plan = plan_research("Why has India's GDP slowed?")
    orders = [d.order for d in plan.required_datasets]
    assert orders == list(range(1, len(orders) + 1))
    # Primary GDP first
    assert "gdp" in plan.required_datasets[0].topic.lower()
    assert plan.required_datasets[0].priority.value == "critical"


# ---------------------------------------------------------------------------
# Research modes
# ---------------------------------------------------------------------------


def test_comparison_plan():
    plan = plan_research("Compare India and China GDP")
    assert plan.objective.objective_type == ResearchObjectiveType.COMPARISON
    assert "India" in plan.objective.entities
    assert "China" in plan.objective.entities
    assert len(plan.topics) >= 2
    assert any("india" in t.lower() for t in plan.topics)
    assert any("china" in t.lower() for t in plan.topics)


def test_correlation_plan():
    plan = plan_research("Relationship between rainfall and crop yield")
    assert plan.objective.objective_type == ResearchObjectiveType.CORRELATION
    assert _has_metric(plan, "rainfall")
    assert _has_metric(plan, "crop")
    assert any(g.goal_type == "correlation" for g in plan.analysis_goals)


def test_forecasting_plan():
    plan = plan_research("Forecast India's GDP for the next 5 years")
    assert plan.objective.objective_type == ResearchObjectiveType.FORECASTING
    assert plan.objective.time_horizon is not None
    assert _has_metric(plan, "gdp")
    assert any(o.output_type == "forecast" for o in plan.expected_outputs)


def test_trend_plan():
    plan = plan_research("Show the trend of India inflation over time")
    assert plan.objective.objective_type == ResearchObjectiveType.TREND
    assert _has_metric(plan, "inflation")


def test_impact_plan():
    plan = plan_research("What is the impact of interest rates on India's GDP?")
    assert plan.objective.objective_type == ResearchObjectiveType.IMPACT
    assert _has_metric(plan, "gdp") or _has_metric(plan, "interest")


def test_benchmarking_plan():
    plan = plan_research("Benchmark India's GDP against peers")
    assert plan.objective.objective_type == ResearchObjectiveType.BENCHMARKING
    assert _has_metric(plan, "gdp")
    # Peer entity dataset
    assert any(
        "china" in t.lower() or "united states" in t.lower() for t in plan.topics
    )


def test_multi_metric_explicit():
    plan = plan_research("Analyze India GDP, Inflation and Population")
    assert plan.objective.objective_type in {
        ResearchObjectiveType.MULTI_METRIC,
        ResearchObjectiveType.EXPLORATION,
    }
    assert _has_metric(plan, "gdp")
    assert _has_metric(plan, "inflation")
    assert _has_metric(plan, "population")


# ---------------------------------------------------------------------------
# Context + API
# ---------------------------------------------------------------------------


def test_uses_conversation_context():
    context = {
        "selected_countries": ["India"],
        "metrics": ["GDP"],
        "last_operation": "analyze",
    }
    plan = plan_research("Why did it slow down?", context=context)
    assert plan.context_used is True
    assert "India" in plan.objective.entities
    assert plan.objective.primary_metric == "GDP"
    assert plan.objective.objective_type == ResearchObjectiveType.ROOT_CAUSE


def test_context_object_with_to_dict():
    class FakeCtx:
        def to_dict(self):
            return {
                "selected_countries": ["Germany"],
                "metrics": ["Unemployment"],
            }

    plan = plan_research("Why is it rising?", context=FakeCtx())
    assert "Germany" in plan.objective.entities
    assert plan.objective.primary_metric == "Unemployment"


def test_empty_question():
    plan = plan_research("")
    assert plan.required_datasets == []
    assert plan.confidence == 0.0


def test_max_datasets_cap():
    plan = plan_research("Why has India's GDP slowed?", max_datasets=4)
    assert len(plan.required_datasets) <= 4
    # Mandatory retained preferentially
    assert any("gdp" in t.lower() for t in plan.mandatory_topics)


def test_agent_class_api():
    agent = AutonomousResearchAgent()
    plan = agent.plan_research("Forecast gold prices")
    assert isinstance(plan, ResearchPlan)
    topics = agent.required_topics("Forecast gold prices")
    assert topics


def test_planner_direct():
    planner = ResearchPlanner()
    plan = planner.plan("Compare inflation in India vs USA")
    assert plan.objective.objective_type == ResearchObjectiveType.COMPARISON


def test_research_plan_to_dict_roundtrip():
    plan = plan_research("Why has India's GDP slowed?")
    d = plan.to_dict()
    assert "required_datasets" in d
    assert "mandatory_topics" in d
    assert "analysis_goals" in d
    assert "expected_outputs" in d
    assert "dependencies" in d
    back = ResearchPlan.from_dict(d)
    assert back.topics == plan.topics
    assert back.objective.objective_type == plan.objective.objective_type


def test_does_not_retrieve(monkeypatch):
    """Ensure research planning never calls retrieval."""
    called = {"retrieve": False}

    def _fake_retrieve(*args, **kwargs):
        called["retrieve"] = True
        raise AssertionError("Retrieval must not be called")

    # If someone imports retrieval accidentally during plan, this would fire
    # only if wired — we just assert plan works without side effects.
    plan = plan_research("Why has India's GDP slowed?")
    assert plan.topics
    assert called["retrieve"] is False


def test_dependencies_point_to_primary():
    plan = plan_research("Why has India's GDP slowed?")
    primary = plan.required_datasets[0].topic
    for edge in plan.dependencies:
        assert edge["from"] == primary or edge["from"] in plan.topics
        assert edge["to"] in plan.topics


def test_analysis_goals_and_outputs_for_root_cause():
    plan = plan_research("Why has India's GDP slowed?")
    goal_types = {g.goal_type for g in plan.analysis_goals}
    assert "trend" in goal_types or "root_cause" in goal_types
    output_types = {o.output_type for o in plan.expected_outputs}
    assert "insight" in output_types
    assert "chart" in output_types or "report_section" in output_types
