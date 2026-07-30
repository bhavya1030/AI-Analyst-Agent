"""LangGraph forecasting agent — thin wrapper over ForecastEngine.

Progressive: forecast failures never wipe EDA/charts already on the state.
Timeout budget prevents HTTP client timeouts (default 10s).
"""

from __future__ import annotations

from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.config import settings
from backend.core.logger import get_logger
from backend.errors.error_types import FORECAST_FAILED, NO_NUMERIC_COLUMN, NO_TIME_COLUMN
from backend.forecast.engine import run_forecast

logger = get_logger(__name__)


def forecasting_agent(state):
    df = state.get("data")
    profile = state.get("dataset_profile") or {}

    # Do not clear unrelated progressive artifacts (EDA/charts/insights)
    state["forecast"] = state.get("forecast") or []
    state["forecast_chart"] = state.get("forecast_chart")
    state["forecast_error"] = None
    state["forecast_partial"] = False
    state["forecast_from_cache"] = False
    state["forecast_model"] = None
    state["forecast_timings"] = {}
    state["forecast_explanation"] = None
    state["forecast_suggested_retry"] = None

    if df is None:
        state["forecast_error"] = "No dataset available for forecasting."
        state["error_type"] = FORECAST_FAILED
        state["forecast_explanation"] = state["forecast_error"]
        # Preserve existing charts/insights
        return state

    time_columns = list(profile.get("time_columns") or [])
    if not time_columns:
        # Best-effort: detect a time-like column from frame
        time_columns = _guess_time_columns(df)
    if not time_columns:
        state["forecast_error"] = "No time column found for forecasting."
        state["error_type"] = NO_TIME_COLUMN
        state["forecast_explanation"] = state["forecast_error"]
        state["forecast_suggested_retry"] = (
            "Provide a dataset with a date/year column, or run EDA first."
        )
        return state

    time_col = time_columns[0]
    numeric_cols = [
        col
        for col in (profile.get("numeric_columns") or _guess_numeric_columns(df))
        if col != time_col
    ]
    if not numeric_cols:
        state["forecast_error"] = "No numeric column found for forecasting."
        state["error_type"] = NO_NUMERIC_COLUMN
        state["forecast_explanation"] = state["forecast_error"]
        return state

    value_col = numeric_cols[0]
    # Prefer focus metric if present
    focus = state.get("focus_metric") or state.get("last_forecast_target")
    if focus:
        for c in numeric_cols:
            if str(c).lower() == str(focus).lower() or str(focus).lower() in str(c).lower():
                value_col = c
                break

    reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
    fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
        df, reference
    )
    state["dataset_fingerprint"] = fingerprint

    horizon = int(
        state.get("forecast_horizon")
        or getattr(settings, "FORECAST_HORIZON", 10)
        or 10
    )
    budget = float(getattr(settings, "FORECAST_TIMEOUT_SECONDS", 10) or 10)

    try:
        result = run_forecast(
            df,
            time_col=time_col,
            value_col=value_col,
            reference=str(reference) if reference else None,
            fingerprint=fingerprint,
            horizon=horizon,
            budget_seconds=budget,
            use_cache=True,
        )
    except Exception as exc:
        # Absolute last resort — never raise into the graph / HTTP layer
        logger.error("Forecast engine crashed", extra={"error": str(exc)})
        state["forecast_error"] = f"Forecast failed: {exc}"
        state["error_type"] = FORECAST_FAILED
        state["forecast_explanation"] = (
            "Forecasting encountered an unexpected error. Existing analysis was preserved."
        )
        state["forecast_suggested_retry"] = "Retry forecast with a simpler yearly series."
        return state

    state["forecast"] = result.forecast or []
    state["forecast_chart"] = result.forecast_chart
    state["forecast_model"] = result.model
    state["forecast_from_cache"] = bool(result.from_cache)
    state["forecast_partial"] = bool(result.partial or result.timed_out)
    state["forecast_timings"] = result.timings.to_dict() if result.timings else {}
    state["forecast_explanation"] = result.explanation
    state["forecast_suggested_retry"] = result.suggested_retry
    state["forecast_fallback_reason"] = result.fallback_reason
    state["forecast_timeout_reason"] = result.timeout_reason
    state["forecast_frequency"] = result.frequency
    state["last_forecast_target"] = value_col
    state["last_columns_used"] = [time_col, value_col]

    if result.success and result.forecast:
        state["last_chart_type"] = "forecast"
        state["forecast_error"] = None
        # Soft warning when partial/timeout
        if result.timed_out or result.partial:
            state["forecast_error"] = None  # still a usable forecast
            if result.explanation and not state.get("answer"):
                pass
    else:
        state["forecast_error"] = result.error or result.explanation or "Forecast unavailable."
        state["error_type"] = FORECAST_FAILED

    # Merge detailed timings into pipeline timings if present
    try:
        from backend.production.pipeline_timing import get_timer, record_stage_ms

        ft = state["forecast_timings"] or {}
        if ft.get("total_ms") is not None:
            record_stage_ms("forecast", float(ft["total_ms"]))
        timer = get_timer()
        if timer is not None:
            for key, stage in (
                ("training_ms", "forecast_training"),
                ("prediction_ms", "forecast_prediction"),
                ("chart_generation_ms", "forecast_chart"),
            ):
                if ft.get(key):
                    timer.add_ms(stage, float(ft[key]))
            if result.model:
                timer.meta["forecast_model"] = result.model
    except Exception:
        pass

    logger.info(
        "Forecasting agent finished",
        extra={
            "action": "forecast_data",
            "model": result.model,
            "success": result.success,
            "partial": result.partial,
            "timed_out": result.timed_out,
            "from_cache": result.from_cache,
            "target": value_col,
            "horizon": horizon,
            "total_ms": (state["forecast_timings"] or {}).get("total_ms"),
            "fallback_reason": result.fallback_reason,
            "timeout_reason": result.timeout_reason,
        },
    )
    return state


def _guess_time_columns(df) -> list[str]:
    cols = []
    for c in df.columns:
        name = str(c).lower()
        if any(tok in name for tok in ("date", "time", "year", "month", "day", "period")):
            cols.append(c)
            continue
        try:
            import pandas as pd

            if pd.api.types.is_datetime64_any_dtype(df[c]):
                cols.append(c)
        except Exception:
            pass
    return cols


def _guess_numeric_columns(df) -> list[str]:
    try:
        import pandas as pd

        return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    except Exception:
        return []
