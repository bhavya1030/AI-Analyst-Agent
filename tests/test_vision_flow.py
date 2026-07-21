"""Product-vision regression tests for automatic analytics orchestration."""

from backend.agents.conversation_context_agent import conversation_context_agent
from backend.agents.dataset_topic_agent import dataset_topic_agent
from backend.agents.dataset_search_agent import dataset_search_agent
from backend.agents.planner_agent import planner_agent, _build_rule_based_plan
from backend.utils.intent_classifier import _fallback_intent_classification


def test_analyze_india_gdp_intents():
    intents = _fallback_intent_classification("Analyze India's GDP")
    assert "dataset_autoload" in intents
    assert "eda" in intents


def test_dataset_topic_india_gdp():
    state = {"question": "Analyze India's GDP"}
    result = dataset_topic_agent(state)
    topic = (result.get("dataset_topic") or "").lower()
    assert "gdp" in topic
    assert result.get("focus_country") == "India"


def test_dataset_search_returns_downloadable_gdp():
    state = {"dataset_topic": "India GDP", "question": "Analyze India's GDP"}
    result = dataset_search_agent(state)
    url = (result.get("dataset_url") or "").lower()
    assert url.endswith(".csv")
    assert "gdp" in url or "gdp" in (result.get("dataset_topic") or "").lower()


def test_full_analysis_plan_includes_pipeline():
    state = {"data": None, "question": "Analyze India's GDP"}
    intents = ["eda", "dataset_autoload"]
    plan = _build_rule_based_plan(state, "analyze india's gdp", intents, dataset_requested=True)
    for step in (
        "dataset_topic_agent",
        "dataset_search_agent",
        "fetch_data",
        "profile_data",
        "run_eda",
        "run_viz",
        "recommend_analysis",
        "generate_insight",
    ):
        assert step in plan, f"missing {step} in {plan}"


def test_follow_up_forecast_it_reuses_dataset(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.conversation_context_agent.classify_intents",
        lambda q: ["forecasting"],
    )
    state = {
        "question": "Forecast it for 10 years",
        "data": object(),
        "dataset_topic": "India GDP",
        "dataset_url": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    }
    ctx = conversation_context_agent(state)
    assert ctx.get("reuse_active_dataset") is True
    assert "forecast" in (ctx.get("question") or "").lower()
    assert "India GDP" in (ctx.get("question") or "")

    monkeypatch.setattr(
        "backend.agents.planner_agent.classify_intents",
        lambda q: ["forecasting"],
    )
    plan_state = planner_agent(ctx)
    plan = plan_state.get("plan") or []
    assert "forecast_data" in plan
    assert "dataset_search_agent" not in plan
    assert "fetch_data" not in plan


def test_compare_plan_priority():
    state = {"data": None, "question": "Compare GDP and Population"}
    intents = ["comparison", "visualization", "dataset_autoload"]
    plan = _build_rule_based_plan(
        state, "compare gdp and population", intents, dataset_requested=True
    )
    assert "compare_datasets" in plan
