"""Orchestration integration: planner + new retrieve/prepare nodes."""

from backend.agents.planner_agent import planner_agent
from backend.graph.workflow import REGISTERED_NODES, ROUTE_MAP, build_graph


def test_planner_discovery_uses_new_pipeline():
    state = {
        "question": "Analyze India GDP",
        "data": None,
        "file_path": None,
        "dataset_url": None,
    }
    result = planner_agent(state)
    plan = result.get("plan") or []
    assert "retrieve_dataset" in plan
    assert "prepare_dataset" in plan
    assert "fetch_data" in plan
    assert plan.index("retrieve_dataset") < plan.index("prepare_dataset")
    assert plan.index("prepare_dataset") < plan.index("fetch_data")
    assert "run_eda" in plan
    assert "run_viz" in plan
    assert "generate_insight" in plan


def test_workflow_registers_new_nodes():
    assert "retrieve_dataset" in REGISTERED_NODES
    assert "prepare_dataset" in REGISTERED_NODES
    assert ROUTE_MAP["retrieve_dataset"] == "retrieve_dataset"
    graph = build_graph()
    assert graph is not None


def test_data_engineer_requires_local_path():
    from backend.agents.data_engineer_agent import data_engineer_agent

    state = {
        "question": "analyze x",
        "dataset_topic": "x",
        "data": None,
        "local_path": None,
        "file_path": None,
        "force_reload_dataset": True,
    }
    out = data_engineer_agent(state)
    assert out.get("stop") is True
    assert out.get("data") is None
    assert "local" in (out.get("error") or "").lower() or "path" in (out.get("error") or "").lower()
