from datetime import datetime

import pandas as pd
import plotly.express as px
from prophet import Prophet

from backend.utils.json_safe import figure_to_json


def _normalize_time_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    cleaned = pd.to_numeric(series, errors="coerce")
    if cleaned.notna().all() and cleaned.between(1800, 2100).all():
        return pd.to_datetime(cleaned.astype(int).astype(str), format="%Y", errors="coerce")

    return pd.to_datetime(series, errors="coerce")


def forecasting_agent(state):
    df = state.get("data")
    profile = state.get("dataset_profile", {})

    state["forecast"] = []
    state["forecast_chart"] = None
    state["forecast_error"] = None

    if df is None:
        state["forecast_error"] = "No dataset available for forecasting."
        return state

    time_columns = profile.get("time_columns", [])
    if not time_columns:
        state["forecast_error"] = "No time column found for forecasting."
        return state

    time_col = time_columns[0]
    numeric_cols = [col for col in profile.get("numeric_columns", []) if col != time_col]
    if not numeric_cols:
        state["forecast_error"] = "No numeric column found for forecasting."
        return state

    value_col = numeric_cols[0]
    series = df[[time_col, value_col]].dropna()
    series = series.copy()
    series["ds"] = _normalize_time_series(series[time_col])
    series["y"] = pd.to_numeric(series[value_col], errors="coerce")
    series = series.dropna(subset=["ds", "y"])

    if len(series) < 10:
        state["forecast_error"] = "Dataset too small for reliable forecasting."
        return state

    try:
        model = Prophet()
        model.fit(series[["ds", "y"]])

        future = model.make_future_dataframe(periods=10)
        forecast = model.predict(future)

        state["forecast"] = forecast.tail(10).to_dict(orient="records")
        fig = px.line(
            forecast,
            x="ds",
            y="yhat",
            labels={"ds": time_col, "yhat": value_col},
            title=f"Forecast for {value_col}",
        )
        fig.add_scatter(x=series["ds"], y=series["y"], mode="markers+lines", name="Historical")
        fig.add_scatter(x=forecast["ds"], y=forecast["yhat_lower"], mode="lines", line=dict(dash="dash"), name="Lower CI")
        fig.add_scatter(x=forecast["ds"], y=forecast["yhat_upper"], mode="lines", line=dict(dash="dash"), name="Upper CI")
        state["forecast_chart"] = figure_to_json(fig)
        state["last_forecast_target"] = value_col

        state["last_chart_type"] = "forecast"
        state["last_columns_used"] = [time_col, value_col]
        return state
    except Exception as exc:
        state["forecast_error"] = f"Forecast failed: {exc}"
        return state
