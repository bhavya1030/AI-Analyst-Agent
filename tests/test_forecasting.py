import pandas as pd

from backend.agents.forecasting_agent import forecasting_agent


def test_forecasting_agent_generates_forecast():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=20, freq="D"),
            "value": range(20),
        }
    )
    state = {
        "data": df,
        "dataset_profile": {"time_columns": ["date"], "numeric_columns": ["value"]},
        "dataset_url": "test_forecast",
    }

    result = forecasting_agent(state)

    assert isinstance(result.get("forecast"), list)
    assert result.get("forecast")
    assert result.get("forecast_error") in (None, "")
    assert result.get("forecast_chart")
