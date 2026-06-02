from backend.agents import dataset_topic_agent as dataset_topic_module
from backend.agents import planner_agent as planner_module
from backend.agents.dataset_search_agent import dataset_search_agent
from backend.agents.dataset_topic_agent import dataset_topic_agent
from backend.agents.planner_agent import planner_agent
from backend.llm import ollama_client
from backend.utils import intent_classifier


def test_planner_uses_llm_planning_for_dataset_search(monkeypatch):
    def fake_invoke_llm(prompt: str) -> str:
        if "You are an analytics intent classifier" in prompt:
            return '{"intents": ["dataset_search", "visualization"]}'
        if "You are an analytics workflow planner" in prompt:
            return '{"plan": ["dataset_topic_agent", "dataset_search_agent", "fetch_data", "profile_data", "run_eda", "run_viz", "generate_insight"]}'
        return ""

    monkeypatch.setattr(ollama_client, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(intent_classifier, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(planner_module, "invoke_llm", fake_invoke_llm)

    state = {
        "question": "Find a GDP dataset and visualize trends",
        "dataset_profile": {},
        "data": None,
        "file_path": None,
    }

    result = planner_agent(state)

    assert result["plan"][0] == "dataset_topic_agent"
    assert "dataset_search_agent" in result["plan"]
    assert "run_eda" in result["plan"]
    assert result["last_operation"] == "visualization"


def test_dataset_topic_and_search_agent_flow(monkeypatch):
    def fake_invoke_llm(prompt: str) -> str:
        if "Extract the dataset topic" in prompt:
            return '{"dataset_topic": "GDP"}'
        return ""

    monkeypatch.setattr(ollama_client, "invoke_llm", fake_invoke_llm)
    monkeypatch.setattr(dataset_topic_module, "invoke_llm", fake_invoke_llm)

    state = {"question": "Analyze GDP growth"}
    topic_state = dataset_topic_agent(state)

    assert topic_state["dataset_topic"] == "GDP"

    search_state = {"dataset_topic": topic_state["dataset_topic"]}
    result_state = dataset_search_agent(search_state)

    assert result_state["dataset_url"] is not None
    assert "gdp" in result_state["dataset_url"].lower()
    assert isinstance(result_state.get("dataset_search_results"), list)
    assert result_state["dataset_topic"] == "GDP"
