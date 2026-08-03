"""Phase 5 Regression Tests — Planner Redesign.

Verifies:
1. Planner does NOT guess dataset names, perform topic discovery, or decide topic mismatches.
2. Active dataset EXISTS + analytical intent NEVER triggers dataset discovery/retrieval nodes.
3. Explicit dataset_switch and dataset_search intents route to discovery/search.
4. Active dataset DOES NOT EXIST + analytical intent triggers acquisition/retrieval.
"""

from __future__ import annotations

import pandas as pd
from backend.agents.planner_agent import planner_agent


DISCOVERY_NODES = {
    "retrieve_dataset",
    "prepare_dataset",
    "dataset_topic_agent",
    "dataset_search_agent",
}


def test_active_dataset_analytical_intents_never_trigger_discovery():
    """Verify that active dataset + analytical intents NEVER include discovery nodes."""
    df = pd.DataFrame({"Age": [22, 38], "Fare": [7.25, 71.28]})
    base_state = {
        "data": df,
        "dataset_name": "titanic.csv",
        "dataset_path": "/data/titanic.csv",
        "dataset_topic": "titanic",
        "has_active_dataset": True,
        "topic_mismatch": False,
    }

    intents_to_test = [
        ("show missing values", ["eda"]),
        ("describe dataset", ["eda"]),
        ("average fare", ["statistics"]),
        ("plot histogram", ["visualization"]),
        ("forecast passengers", ["forecast"]),
        ("compare male vs female", ["comparison"]),
        ("explain this chart", ["chart_explanation"]),
        ("show first 5 rows", ["preview"]),
    ]

    for question, intents in intents_to_test:
        state = {**base_state, "question": question, "intents": intents}
        result = planner_agent(state)
        plan = result["plan"]

        # Must never contain discovery nodes
        assert not DISCOVERY_NODES.intersection(plan), f"Query '{question}' with active dataset included discovery nodes in plan: {plan}"
        assert result.get("reuse_active_dataset") is True


def test_dataset_switch_routes_to_discovery():
    """Verify that dataset_switch intent routes to retrieval/discovery."""
    df = pd.DataFrame({"a": [1]})
    state = {
        "data": df,
        "dataset_topic": "titanic",
        "question": "Analyze GDP",
        "intents": ["dataset_switch"],
        "topic_mismatch": True,
    }
    result = planner_agent(state)
    plan = result["plan"]

    assert "retrieve_dataset" in plan or "prepare_dataset" in plan
    assert result.get("reuse_active_dataset") is False


def test_dataset_search_routes_to_search():
    """Verify that dataset_search intent routes to dataset search/retrieval."""
    state = {
        "question": "search unemployment dataset",
        "intents": ["dataset_search"],
    }
    result = planner_agent(state)
    plan = result["plan"]

    assert "retrieve_dataset" in plan or "prepare_dataset" in plan


def test_no_active_dataset_triggers_retrieval():
    """Verify that analytical query without active dataset triggers retrieval pipeline."""
    state = {
        "question": "show missing values",
        "intents": ["eda"],
        "data": None,
        "dataset_path": None,
        "file_path": None,
    }
    result = planner_agent(state)
    plan = result["plan"]

    assert "retrieve_dataset" in plan or "prepare_dataset" in plan or "load_data" in plan
