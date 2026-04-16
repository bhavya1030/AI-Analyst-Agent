import time

import pandas as pd
import plotly.express as px
from prophet import Prophet

from backend.cache.dataset_cache import get_forecast, set_forecast
from backend.config import settings
from backend.core.logger import get_logger
from backend.errors.error_types import FORECAST_FAILED, NO_NUMERIC_COLUMN, NO_TIME_COLUMN
from backend.utils.json_safe import figure_to_json

logger = get_logger(__name__)


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
    state["error_type"] = None

    if df is None:
        state["forecast_error"] = "No dataset available for forecasting."
        state["error_type"] = FORECAST_FAILED
        return state

    time_columns = profile.get("time_columns", [])
    if not time_columns:
        state["forecast_error"] = "No time column found for forecasting."
        state["error_type"] = NO_TIME_COLUMN
        return state

    time_col = time_columns[0]
    numeric_cols = [col for col in profile.get("numeric_columns", []) if col != time_col]
    if not numeric_cols:
        state["forecast_error"] = "No numeric column found for forecasting."
        state["error_type"] = NO_NUMERIC_COLUMN
        return state

    value_col = numeric_cols[0]
    reference = state.get("dataset_url") or state.get("file_path") or "default"
    cached_forecast = get_forecast(reference, value_col)
    if cached_forecast is not None:
        state["forecast"] = cached_forecast["forecast"]
        state["forecast_chart"] = cached_forecast["forecast_chart"]
        state["last_forecast_target"] = value_col
        logger.info(
            "Forecast served from cache",
            extra={"action": "forecast_data", "dataset": reference, "target": value_col},
        )
        return state

    series = df[[time_col, value_col]].dropna().copy()
    series["ds"] = _normalize_time_series(series[time_col])
    series["y"] = pd.to_numeric(series[value_col], errors="coerce")
    series = series.dropna(subset=["ds", "y"])

    if len(series) < max(10, settings.FORECAST_HORIZON):
        state["forecast_error"] = "Dataset too small for reliable forecasting."
        state["error_type"] = FORECAST_FAILED
        return state

    start_time = time.perf_counter()

    try:
        model = Prophet()
        model.fit(series[["ds", "y"]])

        future = model.make_future_dataframe(periods=settings.FORECAST_HORIZON)
        forecast = model.predict(future)

        state["forecast"] = forecast.tail(settings.FORECAST_HORIZON).to_dict(orient="records")
        fig = px.line(
            forecast,
            x="ds",
            y="yhat",
            labels={"ds": time_col, "yhat": value_col},
            title=f"Forecast for {value_col}",
        )
        fig.add_scatter(x=series["ds"], y=series["y"], mode="markers+lines", name="Historical")
        fig.add_scatter(
            x=forecast["ds"],
            y=forecast["yhat_lower"],
            mode="lines",
            line=dict(dash="dash"),
            name="Lower CI",
        )
        fig.add_scatter(
            x=forecast["ds"],
            y=forecast["yhat_upper"],
            mode="lines",
            line=dict(dash="dash"),
            name="Upper CI",
        )
        state["forecast_chart"] = figure_to_json(fig)
        state["last_forecast_target"] = value_col
        state["last_chart_type"] = "forecast"
        state["last_columns_used"] = [time_col, value_col]
        set_forecast(reference, value_col, state["forecast"], state["forecast_chart"])

        logger.info(
            "Forecast generated",
            extra={
                "action": "forecast_data",
                "dataset": reference,
                "target": value_col,
                "duration_ms": round((time.perf_counter() - start_time) * 1000, 3),
            },
        )
        return state
    except Exception as exc:
        state["forecast_error"] = f"Forecast failed: {exc}"
        state["error_type"] = FORECAST_FAILED
        logger.error(
            "Forecasting failed",
            extra={"action": "forecast_data", "dataset": reference, "error": str(exc)},
        )
        return state
