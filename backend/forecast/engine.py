"""Production forecasting engine — strategy, budget, cache, progressive fallback."""

from __future__ import annotations

import time
from typing import Any, Optional

import pandas as pd

from backend.cache.analysis_cache import KIND_FORECAST, get_analysis_cache
from backend.cache.dataset_cache import get_forecast, remember_fingerprint, set_forecast
from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.config import settings
from backend.core.logger import get_logger
from backend.forecast.methods import build_forecast_chart, run_model
from backend.forecast.models import ForecastResult, ForecastTimings
from backend.forecast.strategy import infer_series_profile, select_strategy
from backend.forecast.timeout import run_with_budget

logger = get_logger(__name__)


def _prophet_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("prophet") is not None
    except Exception:
        return False


def _arima_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("statsmodels") is not None
    except Exception:
        return False


def _normalize_time_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    cleaned = pd.to_numeric(series, errors="coerce")
    if cleaned.notna().sum() >= max(2, int(0.8 * len(series))):
        if cleaned.dropna().between(1800, 2100).mean() >= 0.9:
            return pd.to_datetime(
                cleaned.round().astype("Int64").astype(str), format="%Y", errors="coerce"
            )
    return pd.to_datetime(series, errors="coerce")


def _prepare_series(
    df: pd.DataFrame, time_col: str, value_col: str
) -> pd.DataFrame:
    series = df[[time_col, value_col]].copy()
    series["ds"] = _normalize_time_series(series[time_col])
    series["y"] = pd.to_numeric(series[value_col], errors="coerce")
    series = series.dropna(subset=["ds", "y"]).sort_values("ds")
    # Drop duplicate timestamps (keep last)
    series = series.drop_duplicates(subset=["ds"], keep="last")
    return series.reset_index(drop=True)


def _cache_params(
    *,
    target: str,
    time_col: str,
    horizon: int,
    model: str,
) -> dict[str, Any]:
    return {
        "target": target,
        "time_col": time_col,
        "horizon": int(horizon),
        "model": model,
        "engine": "forecast_v2",
    }


class ForecastEngine:
    """Budgeted multi-strategy forecasting with cache and progressive fallback."""

    def __init__(
        self,
        *,
        budget_seconds: float | None = None,
        horizon: int | None = None,
    ):
        self.budget_seconds = float(
            budget_seconds
            if budget_seconds is not None
            else getattr(settings, "FORECAST_TIMEOUT_SECONDS", 10) or 10
        )
        self.horizon = int(
            horizon if horizon is not None else getattr(settings, "FORECAST_HORIZON", 10) or 10
        )

    def run(
        self,
        df: pd.DataFrame,
        *,
        time_col: str,
        value_col: str,
        reference: str | None = None,
        fingerprint: str | None = None,
        horizon: int | None = None,
        use_cache: bool = True,
    ) -> ForecastResult:
        t0 = time.perf_counter()
        timings = ForecastTimings()
        horizon = int(horizon if horizon is not None else self.horizon)
        result = ForecastResult(
            time_col=time_col,
            value_col=value_col,
            horizon=horizon,
        )

        if df is None or not len(df):
            result.error = "No dataset available for forecasting."
            result.explanation = "Upload or load a dataset before forecasting."
            result.suggested_retry = "Provide a time series with a date column and a numeric metric."
            return result

        fp = fingerprint or compute_dataset_fingerprint(df, reference)
        if reference:
            remember_fingerprint(reference, fp)

        # Prepare series first (cheap) so strategy + cache key are accurate
        try:
            series = _prepare_series(df, time_col, value_col)
        except Exception as exc:
            result.error = f"Could not prepare time series: {exc}"
            result.explanation = "Time or value columns could not be parsed for forecasting."
            result.suggested_retry = "Ensure the time column is parseable and the metric is numeric."
            return result

        result.n_points = len(series)
        if result.n_points < 2:
            result.model = "unsupported"
            result.error = "Dataset too small for forecasting (need ≥2 points)."
            result.explanation = (
                f"Only {result.n_points} valid observation(s) after cleaning missing values."
            )
            result.suggested_retry = "Provide a longer history or fill missing values."
            result.fallback_reason = "insufficient_points"
            return result

        t_sel = time.perf_counter()
        profile = infer_series_profile(series["ds"])
        result.frequency = profile.frequency
        choice = select_strategy(
            profile,
            prophet_available=_prophet_available()
            and bool(getattr(settings, "FORECAST_ALLOW_PROPHET", False)),
            arima_available=_arima_available(),
            budget_seconds=self.budget_seconds,
            allow_prophet=bool(getattr(settings, "FORECAST_ALLOW_PROPHET", False)),
        )
        timings.strategy_select_ms = (time.perf_counter() - t_sel) * 1000
        result.model = choice.model
        result.params = _cache_params(
            target=value_col,
            time_col=time_col,
            horizon=horizon,
            model=choice.model,
        )

        if choice.model == "unsupported":
            result.error = choice.reason
            result.explanation = choice.reason
            result.fallback_reason = "unsupported"
            result.suggested_retry = "Provide a longer time series."
            timings.total_ms = (time.perf_counter() - t0) * 1000
            result.timings = timings
            return result

        # Cache lookup (fingerprint + params + horizon + model)
        if use_cache:
            t_c = time.perf_counter()
            cached = self._cache_get(fp, reference, result.params)
            timings.cache_lookup_ms = (time.perf_counter() - t_c) * 1000
            if cached is not None:
                result.forecast = cached.get("forecast") or []
                result.forecast_chart = cached.get("forecast_chart")
                result.success = bool(result.forecast)
                result.from_cache = True
                result.explanation = (
                    f"Served cached {choice.model} forecast "
                    f"(horizon={horizon}, n={result.n_points})."
                )
                if cached.get("model"):
                    result.model = str(cached.get("model"))
                timings.total_ms = (time.perf_counter() - t0) * 1000
                result.timings = timings
                logger.info(
                    "Forecast cache hit",
                    extra={
                        "model": result.model,
                        "fingerprint": fp[:16],
                        "horizon": horizon,
                        "target": value_col,
                    },
                )
                return result

        # Budgeted training + prediction
        remaining = max(
            0.5,
            self.budget_seconds - (time.perf_counter() - t0) - 0.5,  # reserve chart time
        )

        def _fit_predict() -> tuple[list[dict[str, Any]], float, float, str, Optional[str]]:
            model_name = choice.model
            try:
                recs, train_ms, pred_ms = run_model(
                    model_name,
                    series,
                    horizon,
                    seasonal_period=choice.seasonal_period,
                )
                return recs, train_ms, pred_ms, model_name, None
            except Exception as exc:
                # Progressive fallback chain
                fallbacks = []
                if model_name not in {"linear", "trend"}:
                    fallbacks.append("linear")
                if model_name != "trend":
                    fallbacks.append("trend")
                last_err = str(exc)
                for fb in fallbacks:
                    try:
                        recs, train_ms, pred_ms = run_model(
                            fb, series, horizon, seasonal_period=choice.seasonal_period
                        )
                        return recs, train_ms, pred_ms, fb, f"{model_name}_failed:{last_err}"
                    except Exception as exc2:
                        last_err = str(exc2)
                raise RuntimeError(last_err) from exc

        budgeted = run_with_budget(
            _fit_predict,
            budget_seconds=remaining,
            label=f"model={choice.model}",
        )

        if budgeted.timed_out:
            # Partial: instant trend projection outside budget thread (must be fast)
            result.timed_out = True
            result.timeout_reason = budgeted.error or "forecast_budget_exceeded"
            result.partial = True
            result.fallback_reason = "timeout_trend_projection"
            try:
                recs, train_ms, pred_ms = run_model("trend", series, horizon)
                result.forecast = recs
                result.model = "trend"
                result.success = True
                timings.training_ms = train_ms
                timings.prediction_ms = pred_ms
                result.explanation = (
                    f"Forecast budget ({self.budget_seconds:.0f}s) exceeded while running "
                    f"{choice.model}. Returned a partial trend projection instead."
                )
                result.suggested_retry = (
                    "Retry with a smaller horizon, or set FORECAST_TIMEOUT_SECONDS higher "
                    "for heavier models."
                )
            except Exception as exc:
                result.success = False
                result.error = f"Forecast timed out and partial fallback failed: {exc}"
                result.explanation = result.timeout_reason or "Forecast timed out."
                result.suggested_retry = "Retry with more history or a shorter horizon."
        elif budgeted.error:
            result.success = False
            result.error = budgeted.error
            result.explanation = f"Forecast failed: {budgeted.error}"
            result.suggested_retry = "Check that the metric column is numeric and time is ordered."
            result.fallback_reason = "model_error"
        else:
            recs, train_ms, pred_ms, model_used, fb_reason = budgeted.value
            result.forecast = recs
            result.model = model_used
            result.success = bool(recs)
            result.fallback_reason = fb_reason
            timings.training_ms = train_ms
            timings.prediction_ms = pred_ms
            result.explanation = (
                f"Forecast using {model_used} on {result.n_points} points "
                f"({profile.frequency}, horizon={horizon}). {choice.reason}"
            )
            if fb_reason:
                result.explanation += f" Fallback applied: {fb_reason}."

        # Chart generation (independent; never blocks more than remaining budget)
        if result.forecast:
            t_chart = time.perf_counter()
            chart_budget = max(
                0.3,
                self.budget_seconds - (time.perf_counter() - t0),
            )

            def _chart():
                return build_forecast_chart(
                    series,
                    result.forecast,
                    time_col=time_col,
                    value_col=value_col,
                    title=f"Forecast for {value_col} ({result.model})",
                )

            chart_res = run_with_budget(
                _chart, budget_seconds=chart_budget, label="chart"
            )
            timings.chart_generation_ms = (time.perf_counter() - t_chart) * 1000
            if chart_res.timed_out:
                result.partial = True
                result.timeout_reason = (result.timeout_reason or "") + ";chart_timeout"
                # leave chart None — EDA/charts from other agents still available
            elif chart_res.error:
                logger.warning("Forecast chart failed", extra={"error": chart_res.error})
            else:
                result.forecast_chart = chart_res.value

        # Cache successful (including partial trend) forecasts
        if use_cache and result.success and result.forecast:
            cache_params = _cache_params(
                target=value_col,
                time_col=time_col,
                horizon=horizon,
                model=result.model,
            )
            result.params = cache_params
            payload = {
                "forecast": result.forecast,
                "forecast_chart": result.forecast_chart,
                "model": result.model,
                "explanation": result.explanation,
                "partial": result.partial,
            }
            try:
                get_analysis_cache().put(KIND_FORECAST, fp, payload, cache_params)
                set_forecast(
                    reference,
                    value_col,
                    result.forecast,
                    result.forecast_chart,
                    fingerprint=fp,
                    horizon=horizon,
                    time_col=time_col,
                    model=result.model,
                )
            except Exception as exc:
                logger.debug("Forecast cache put failed", extra={"error": str(exc)})

        timings.total_ms = (time.perf_counter() - t0) * 1000
        result.timings = timings

        logger.info(
            "Forecast complete",
            extra={
                "model": result.model,
                "success": result.success,
                "partial": result.partial,
                "timed_out": result.timed_out,
                "training_ms": timings.training_ms,
                "prediction_ms": timings.prediction_ms,
                "chart_ms": timings.chart_generation_ms,
                "total_ms": timings.total_ms,
                "fallback_reason": result.fallback_reason,
                "timeout_reason": result.timeout_reason,
                "n_points": result.n_points,
                "horizon": horizon,
                "frequency": result.frequency,
                "from_cache": result.from_cache,
            },
        )
        return result

    def _cache_get(
        self,
        fingerprint: str,
        reference: str | None,
        params: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        try:
            durable = get_analysis_cache().get(KIND_FORECAST, fingerprint, params)
            if isinstance(durable, dict) and durable.get("forecast"):
                return durable
        except Exception:
            pass
        try:
            # Legacy / RAM path — also try without model key via dataset_cache
            hit = get_forecast(
                reference,
                params.get("target") or "",
                fingerprint=fingerprint,
                horizon=params.get("horizon"),
                time_col=params.get("time_col"),
            )
            if isinstance(hit, dict) and hit.get("forecast"):
                return hit
        except Exception:
            pass
        return None


def run_forecast(
    df: pd.DataFrame,
    *,
    time_col: str,
    value_col: str,
    reference: str | None = None,
    fingerprint: str | None = None,
    horizon: int | None = None,
    budget_seconds: float | None = None,
    use_cache: bool = True,
) -> ForecastResult:
    """Module-level entrypoint."""
    engine = ForecastEngine(budget_seconds=budget_seconds, horizon=horizon)
    return engine.run(
        df,
        time_col=time_col,
        value_col=value_col,
        reference=reference,
        fingerprint=fingerprint,
        horizon=horizon,
        use_cache=use_cache,
    )
