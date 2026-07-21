import pandas as pd

from backend.agents.comparison_agent import (
    comparison_agent,
    detect_requested_countries,
    detect_requested_datasets,
)
from backend.agents.planner_agent import _build_rule_based_plan, planner_agent


def test_detect_india_us_countries():
    countries = detect_requested_countries(
        "compare gdp of india with us and plot graph"
    )
    assert "India" in countries
    assert "United States" in countries
    assert len(countries) >= 2


def test_detect_gdp_dataset_keyword():
    datasets = detect_requested_datasets("compare gdp of india with us and plot graph")
    assert datasets == ["gdp"]


def test_country_comparison_with_local_frame():
    df = pd.DataFrame(
        {
            "Country Name": [
                "India",
                "India",
                "United States",
                "United States",
                "China",
                "China",
            ],
            "Year": [2020, 2021, 2020, 2021, 2020, 2021],
            "Value": [2.0e12, 2.2e12, 20.0e12, 21.0e12, 14.0e12, 15.0e12],
        }
    )
    state = {
        "data": df,
        "question": "compare gdp of india with us and plot graph",
    }

    result = comparison_agent(state)

    assert result.get("chart"), "expected a plotly chart payload"
    assert result.get("charts"), "expected charts list for the UI"
    assert result.get("error") in (None, "")
    answer = (result.get("answer") or "").lower()
    assert "india" in answer
    assert "united states" in answer
    assert result.get("last_chart_type") == "line"


def test_metric_comparison_still_requires_two_datasets():
    state = {
        "data": None,
        "question": "compare gdp only",
    }
    result = comparison_agent(state)
    assert "two" in (result.get("answer") or "").lower() or "countries" in (
        result.get("answer") or ""
    ).lower()


def test_planner_routes_compare_before_autoload():
    question = "compare gdp of india with us and plot graph"
    intents = ["visualization", "comparison", "dataset_autoload"]
    state = {"data": None, "question": question}
    plan = _build_rule_based_plan(state, question.lower(), intents, dataset_requested=True)
    assert "compare_datasets" in plan
    assert plan.index("compare_datasets") < plan.index("generate_insight")


def test_planner_agent_injects_compare_datasets(monkeypatch):
    # Force LLM planner empty so rule-based path is used after intent classification.
    monkeypatch.setattr(
        "backend.agents.planner_agent._build_llm_plan",
        lambda question, dataset_available: [],
    )
    monkeypatch.setattr(
        "backend.agents.planner_agent.classify_intents",
        lambda question: ["comparison", "visualization", "dataset_autoload"],
    )

    state = {
        "data": None,
        "question": "compare gdp of india with us and plot graph",
    }
    result = planner_agent(state)
    assert "compare_datasets" in (result.get("plan") or [])
