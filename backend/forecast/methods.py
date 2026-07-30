"""Fast forecasting methods (no heavy imports at module load)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from backend.core.logger import get_logger

logger = get_logger(__name__)


def serialize_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in df.to_dict(orient="records"):
        item = dict(row)
        ds = item.get("ds")
        if isinstance(ds, pd.Timestamp):
            item["ds"] = ds.isoformat()
        # Ensure JSON-friendly floats
        for k, v in list(item.items()):
            if isinstance(v, (np.floating, float)):
                item[k] = float(v)
            elif isinstance(v, (np.integer, int)) and not isinstance(v, bool):
                item[k] = int(v)
        records.append(item)
    return records


def infer_freq_string(ds: pd.Series, fallback: str = "D") -> str:
    try:
        freq = pd.infer_freq(ds)
        if freq:
            return freq
    except Exception:
        pass
    # Heuristic from median delta
    s = pd.to_datetime(ds).sort_values()
    if len(s) < 2:
        return fallback
    delta_td = s.diff().dropna()
    if hasattr(delta_td, "dt"):
        med = (delta_td.dt.total_seconds() / 86400.0).median()
    else:
        med = (delta_td.total_seconds() / 86400.0).median()
    if med >= 300:
        return "YS"
    if 20 <= med <= 45:
        return "MS"
    if 5 <= med <= 10:
        return "W"
    return fallback


def build_future_index(ds: pd.Series, horizon: int) -> pd.DatetimeIndex:
    s = pd.to_datetime(ds).sort_values()
    last = s.iloc[-1]
    freq = infer_freq_string(s, "D")
    try:
        return pd.date_range(start=last, periods=horizon + 1, freq=freq)[1:]
    except Exception:
        # Manual yearly / monthly steps
        if freq in {"YS", "Y", "A", "AS"}:
            return pd.DatetimeIndex(
                [last + pd.DateOffset(years=i) for i in range(1, horizon + 1)]
            )
        if freq in {"MS", "M", "ME"}:
            return pd.DatetimeIndex(
                [last + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
            )
        return pd.date_range(start=last, periods=horizon + 1, freq="D")[1:]


def forecast_trend(
    series: pd.DataFrame, horizon: int
) -> tuple[list[dict[str, Any]], float, float]:
    """Simple last-value + slope trend for tiny datasets."""
    import time

    t_train = time.perf_counter()
    y = series["y"].to_numpy(dtype=float)
    n = len(y)
    if n == 1:
        slope = 0.0
        last = float(y[0])
    else:
        x = np.arange(n, dtype=float)
        slope = float(np.polyfit(x, y, 1)[0])
        last = float(y[-1])
    train_ms = (time.perf_counter() - t_train) * 1000

    t_pred = time.perf_counter()
    future_ds = build_future_index(series["ds"], horizon)
    preds = [last + slope * (i + 1) for i in range(horizon)]
    if n >= 3:
        x = np.arange(n, dtype=float)
        fitted = np.polyval(np.polyfit(x, y, 1), x)
        sigma = float(np.std(y - fitted))
    else:
        sigma = abs(slope) if slope else abs(last) * 0.05
    out = pd.DataFrame(
        {
            "ds": future_ds,
            "yhat": preds,
            "yhat_lower": [p - 1.96 * sigma for p in preds],
            "yhat_upper": [p + 1.96 * sigma for p in preds],
        }
    )
    pred_ms = (time.perf_counter() - t_pred) * 1000
    return serialize_records(out), train_ms, pred_ms

def forecast_linear(
    series: pd.DataFrame, horizon: int
) -> tuple[list[dict[str, Any]], float, float]:
    """Linear regression on time (fast default)."""
    import time

    from sklearn.linear_model import LinearRegression

    t_train = time.perf_counter()
    x = (series["ds"].astype("int64") // 10**9).to_numpy().reshape(-1, 1)
    y = series["y"].to_numpy(dtype=float)
    model = LinearRegression()
    model.fit(x, y)
    train_ms = (time.perf_counter() - t_train) * 1000

    t_pred = time.perf_counter()
    future_ds = build_future_index(series["ds"], horizon)
    future_x = (future_ds.astype("int64") // 10**9).to_numpy().reshape(-1, 1)
    preds = model.predict(future_x)
    resid = y - model.predict(x)
    sigma = float(np.std(resid)) if len(resid) else 0.0
    out = pd.DataFrame(
        {
            "ds": future_ds,
            "yhat": preds,
            "yhat_lower": preds - 1.96 * sigma,
            "yhat_upper": preds + 1.96 * sigma,
        }
    )
    pred_ms = (time.perf_counter() - t_pred) * 1000
    return serialize_records(out), train_ms, pred_ms


def forecast_holt_winters(
    series: pd.DataFrame,
    horizon: int,
    seasonal_period: int = 12,
) -> tuple[list[dict[str, Any]], float, float]:
    """Holt-Winters via statsmodels if available, else damped linear seasonal naive."""
    import time

    y = series["y"].to_numpy(dtype=float)
    n = len(y)
    period = max(2, int(seasonal_period or 12))

    t_train = time.perf_counter()
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        # Additive seasonality when enough history
        seasonal = "add" if n >= 2 * period else None
        model = ExponentialSmoothing(
            y,
            trend="add",
            seasonal=seasonal,
            seasonal_periods=period if seasonal else None,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True, use_brute=False)
        train_ms = (time.perf_counter() - t_train) * 1000
        t_pred = time.perf_counter()
        preds = np.asarray(fitted.forecast(horizon), dtype=float)
        resid = y - np.asarray(fitted.fittedvalues, dtype=float)
        sigma = float(np.nanstd(resid)) if len(resid) else 0.0
    except Exception as exc:
        logger.info(
            "Holt-Winters unavailable/fallback",
            extra={"error": str(exc)},
        )
        # Seasonal naive + linear trend
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        train_ms = (time.perf_counter() - t_train) * 1000
        t_pred = time.perf_counter()
        preds = []
        for i in range(1, horizon + 1):
            seasonal = y[-period + ((i - 1) % period)] - y[-period:].mean() if n >= period else 0.0
            preds.append(float(intercept + slope * (n - 1 + i) + seasonal * 0.5))
        preds = np.asarray(preds, dtype=float)
        sigma = float(np.std(y - (intercept + slope * x))) if n >= 3 else 0.0

    future_ds = build_future_index(series["ds"], horizon)
    out = pd.DataFrame(
        {
            "ds": future_ds,
            "yhat": preds,
            "yhat_lower": preds - 1.96 * sigma,
            "yhat_upper": preds + 1.96 * sigma,
        }
    )
    pred_ms = (time.perf_counter() - t_pred) * 1000
    return serialize_records(out), train_ms, pred_ms


def forecast_arima(
    series: pd.DataFrame, horizon: int
) -> tuple[list[dict[str, Any]], float, float]:
    """Lightweight ARIMA (1,1,1) via statsmodels."""
    import time

    from statsmodels.tsa.arima.model import ARIMA

    y = series["y"].to_numpy(dtype=float)
    t_train = time.perf_counter()
    model = ARIMA(y, order=(1, 1, 1))
    fitted = model.fit()
    train_ms = (time.perf_counter() - t_train) * 1000

    t_pred = time.perf_counter()
    fc = fitted.get_forecast(steps=horizon)
    pred = np.asarray(fc.predicted_mean, dtype=float)
    try:
        ci = fc.conf_int(alpha=0.05)
        lower = np.asarray(ci.iloc[:, 0] if hasattr(ci, "iloc") else ci[:, 0], dtype=float)
        upper = np.asarray(ci.iloc[:, 1] if hasattr(ci, "iloc") else ci[:, 1], dtype=float)
    except Exception:
        sigma = float(np.std(y)) * 0.1
        lower = pred - 1.96 * sigma
        upper = pred + 1.96 * sigma
    future_ds = build_future_index(series["ds"], horizon)
    out = pd.DataFrame(
        {"ds": future_ds, "yhat": pred, "yhat_lower": lower, "yhat_upper": upper}
    )
    pred_ms = (time.perf_counter() - t_pred) * 1000
    return serialize_records(out), train_ms, pred_ms


def forecast_prophet(
    series: pd.DataFrame, horizon: int
) -> tuple[list[dict[str, Any]], float, float]:
    """Optional Prophet — only when explicitly selected and available."""
    import time

    from prophet import Prophet

    t_train = time.perf_counter()
    model = Prophet()
    model.fit(series[["ds", "y"]])
    train_ms = (time.perf_counter() - t_train) * 1000

    t_pred = time.perf_counter()
    future = model.make_future_dataframe(periods=horizon)
    forecast = model.predict(future)
    tail = forecast.tail(horizon)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    pred_ms = (time.perf_counter() - t_pred) * 1000
    return serialize_records(tail), train_ms, pred_ms


def build_forecast_chart(
    history: pd.DataFrame,
    forecast_records: list[dict[str, Any]],
    *,
    time_col: str,
    value_col: str,
    title: Optional[str] = None,
) -> Any:
    """Build plotly forecast chart; returns JSON-safe figure dict/string."""
    import plotly.express as px

    from backend.utils.json_safe import figure_to_json

    if not forecast_records:
        return None

    fc = pd.DataFrame(forecast_records)
    if "ds" in fc.columns:
        fc["ds"] = pd.to_datetime(fc["ds"], errors="coerce")
    fig = px.line(
        fc,
        x="ds",
        y="yhat",
        labels={"ds": time_col, "yhat": value_col},
        title=title or f"Forecast for {value_col}",
    )
    fig.add_scatter(
        x=history["ds"],
        y=history["y"],
        mode="markers+lines",
        name="Historical",
    )
    if "yhat_lower" in fc.columns and "yhat_upper" in fc.columns:
        fig.add_scatter(
            x=fc["ds"],
            y=fc["yhat_lower"],
            mode="lines",
            line=dict(dash="dash"),
            name="Lower CI",
        )
        fig.add_scatter(
            x=fc["ds"],
            y=fc["yhat_upper"],
            mode="lines",
            line=dict(dash="dash"),
            name="Upper CI",
        )
    return figure_to_json(fig)


def run_model(
    model: str,
    series: pd.DataFrame,
    horizon: int,
    *,
    seasonal_period: Optional[int] = None,
) -> tuple[list[dict[str, Any]], float, float]:
    if model == "trend":
        return forecast_trend(series, horizon)
    if model == "linear":
        return forecast_linear(series, horizon)
    if model == "holt_winters":
        return forecast_holt_winters(series, horizon, seasonal_period=seasonal_period or 12)
    if model == "arima":
        return forecast_arima(series, horizon)
    if model == "prophet":
        return forecast_prophet(series, horizon)
    raise ValueError(f"Unknown model: {model}")
