"""Open-world data acquisition: search, resolve, upload/URL guidance."""

from backend.agents.dataset_topic_agent import dataset_topic_agent
from backend.agents.planner_agent import planner_agent
from backend.utils.intent_classifier import classify_intents
from backend.utils.dataset_resolver import is_loadable_url, looks_like_direct_url


def test_open_world_intent_for_free_form_topic():
    intents = classify_intents("Analyze global literacy rates")
    assert "dataset_autoload" in intents or "eda" in intents


def test_topic_agent_extracts_free_form_topic():
    state = dataset_topic_agent({"question": "Explore renewable energy adoption trends"})
    topic = (state.get("dataset_topic") or "").lower()
    assert "renewable" in topic or "energy" in topic
    assert state.get("search_queries")


def test_topic_agent_detects_direct_url():
    url = "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv"
    state = dataset_topic_agent({"question": f"Analyze this {url}"})
    assert state.get("dataset_url") == url
    assert state.get("source") == "direct_url"


def test_planner_discovers_for_open_world_question():
    state = {
        "question": "Analyze global literacy rates",
        "data": None,
        "file_path": None,
        "dataset_url": None,
    }
    result = planner_agent(state)
    plan = result.get("plan") or []
    assert "dataset_topic_agent" in plan or "fetch_data" in plan
    assert "generate_insight" in plan


def test_planner_uses_upload_when_file_present():
    state = {
        "question": "analyze dataset",
        "data": None,
        "file_path": "data/employees.csv",
    }
    result = planner_agent(state)
    plan = result.get("plan") or []
    assert "load_data" in plan


def test_loadable_url_helpers():
    assert is_loadable_url("https://example.com/data.csv")
    assert is_loadable_url("https://example.com/path/file.parquet")
    assert not is_loadable_url("https://example.com/landing-page")
    assert looks_like_direct_url("https://catalog.data.gov/dataset/x")
