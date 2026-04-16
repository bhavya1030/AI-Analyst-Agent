import pandas as pd

from backend.agents.planner_agent import planner_agent


def test_planner_routes_forecast_intent():
    state = {
        "question": "Please forecast sales",
        "dataset_profile": {"time_columns": ["date"], "numeric_columns": ["sales"]},
        "data": None,
        "file_path": "data/sales.csv",
    }

    result = planner_agent(state)

    assert "forecast_data" in result["plan"]
    assert result["last_operation"] == "forecast"
    assert result["last_intent"] is not None


def test_planner_falls_back_for_invalid_node():
    state = {
        "question": "Make a strange request",
        "dataset_profile": {},
        "data": None,
        "file_path": "data/sales.csv",
        "plan": ["invalid_node"],
    }

    result = planner_agent(state)
    assert result["plan"] == ["generate_insight"]
