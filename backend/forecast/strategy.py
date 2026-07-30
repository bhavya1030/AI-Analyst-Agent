"""Automatic forecast strategy selection from series characteristics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SeriesProfile:
    n_points: int
    frequency: str  # yearly | monthly | weekly | daily | irregular | unknown
    seasonal_period: Optional[int]
    span_days: float
    is_monotonic_time: bool


@dataclass(frozen=True)
class StrategyChoice:
    model: str
    reason: str
    seasonal_period: Optional[int] = None


def infer_series_profile(ds: pd.Series) -> SeriesProfile:
    """Infer sampling frequency from a datetime series."""
    s = pd.Series(pd.to_datetime(ds, errors="coerce")).dropna().sort_values()
    s = s.reset_index(drop=True)
    n = len(s)
    if n < 2:
        return SeriesProfile(
            n_points=n,
            frequency="unknown",
            seasonal_period=None,
            span_days=0.0,
            is_monotonic_time=True,
        )

    delta_td = s.diff().dropna()
    try:
        day_vals = delta_td.dt.total_seconds().to_numpy(dtype=float) / 86400.0
    except Exception:
        day_vals = np.array(
            [float(getattr(x, "total_seconds", lambda: 0.0)()) / 86400.0 for x in delta_td],
            dtype=float,
        )
    med = float(np.median(day_vals)) if len(day_vals) else 0.0
    span_days = float((s.iloc[-1] - s.iloc[0]).total_seconds() / 86400.0)
    mono = bool(s.is_monotonic_increasing)

    # Classify by median gap
    if 25 <= med <= 400:  # ~monthly to yearly
        if med >= 300:
            freq, period = "yearly", None
        elif 20 <= med <= 45:
            freq, period = "monthly", 12
        else:
            freq, period = "irregular", None
    elif 5 <= med <= 10:
        freq, period = "weekly", 52
    elif 0.5 <= med <= 2.5:
        freq, period = "daily", 7
    elif med < 0.5 and med > 0:
        freq, period = "daily", 7
    else:
        # Fallback using count vs span
        if span_days > 0 and n >= 2:
            avg = span_days / max(n - 1, 1)
            if avg >= 300:
                freq, period = "yearly", None
            elif 20 <= avg <= 45:
                freq, period = "monthly", 12
            elif avg <= 2:
                freq, period = "daily", 7
            else:
                freq, period = "irregular", None
        else:
            freq, period = "unknown", None

    return SeriesProfile(
        n_points=n,
        frequency=freq,
        seasonal_period=period,
        span_days=span_days,
        is_monotonic_time=mono,
    )


def select_strategy(
    profile: SeriesProfile,
    *,
    prophet_available: bool = False,
    arima_available: bool = False,
    budget_seconds: float = 10.0,
    allow_prophet: bool | None = None,
) -> StrategyChoice:
    """
    Choose algorithm for the series.

    - <8 points → trend projection
    - yearly / short series → linear regression
    - monthly seasonal → Holt-Winters
    - daily seasonal → Prophet (optional) else Holt-Winters
    - long trend → ARIMA if available else linear
    """
    n = profile.n_points
    freq = profile.frequency

    if n < 2:
        return StrategyChoice(
            model="unsupported",
            reason="Fewer than 2 valid observations; cannot forecast.",
        )

    if n < 8:
        return StrategyChoice(
            model="trend",
            reason=f"Very small dataset ({n} rows) → simple trend projection.",
        )

    # Tight budget: prefer fast models only
    prefer_fast = budget_seconds <= 15
    if allow_prophet is None:
        try:
            from backend.config import settings

            allow_prophet = bool(getattr(settings, "FORECAST_ALLOW_PROPHET", False))
        except Exception:
            allow_prophet = False

    if freq == "yearly" or (freq in {"unknown", "irregular"} and n <= 40):
        return StrategyChoice(
            model="linear",
            reason=f"Short/yearly series (n={n}, freq={freq}) → linear regression.",
        )

    if freq == "monthly" and n >= 18:
        return StrategyChoice(
            model="holt_winters",
            reason="Monthly seasonal series → Holt-Winters exponential smoothing.",
            seasonal_period=12,
        )

    if freq == "monthly":
        return StrategyChoice(
            model="linear",
            reason=f"Monthly series too short for seasonality (n={n}) → linear.",
        )

    if freq == "daily" and n >= 30:
        if (
            prophet_available
            and allow_prophet
            and not prefer_fast
            and budget_seconds >= 20
        ):
            return StrategyChoice(
                model="prophet",
                reason="Daily seasonal series with large budget → Prophet.",
                seasonal_period=7,
            )
        if n >= 21:
            return StrategyChoice(
                model="holt_winters",
                reason="Daily seasonal series → Holt-Winters (fast path).",
                seasonal_period=7,
            )
        return StrategyChoice(
            model="linear",
            reason="Daily series without enough seasonality history → linear.",
        )

    if freq == "weekly" and n >= 24:
        return StrategyChoice(
            model="holt_winters",
            reason="Weekly seasonal series → Holt-Winters.",
            seasonal_period=52 if n >= 104 else 4,
        )

    # Long trend series
    if n >= 50 and arima_available and not prefer_fast:
        return StrategyChoice(
            model="arima",
            reason=f"Long trend series (n={n}) → ARIMA.",
        )

    if n >= 30:
        return StrategyChoice(
            model="linear",
            reason=f"Long series without clear seasonality (n={n}) → linear regression.",
        )

    return StrategyChoice(
        model="linear",
        reason=f"Default fast path (n={n}, freq={freq}) → linear regression.",
    )
