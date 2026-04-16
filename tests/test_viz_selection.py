import pandas as pd

from backend.agents.viz_agent import viz_agent


def test_viz_agent_selects_line_for_time_series():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=12, freq="M"),
            "value": range(12),
        }
    )
    state = {
        "data": df,
        "dataset_profile": {"time_columns": ["date"], "numeric_columns": ["value"]},
        "question": "Show me the trend",
    }

    result = viz_agent(state)

    assert result["chart"] is not None
    assert result["chart_columns_used"] == ["date", "value"]
    assert result.get("chart_error") in (None, "")
