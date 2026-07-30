"""Forecast pipeline result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class ForecastTimings:
    """Millisecond timings for forecast sub-stages."""

    strategy_select_ms: float = 0.0
    training_ms: float = 0.0
    prediction_ms: float = 0.0
    chart_generation_ms: float = 0.0
    total_ms: float = 0.0
    cache_lookup_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in asdict(self).items()}


@dataclass
class ForecastResult:
    """Structured output of the forecasting engine."""

    forecast: list[dict[str, Any]] = field(default_factory=list)
    forecast_chart: Any = None
    model: str = "none"
    success: bool = False
    partial: bool = False
    from_cache: bool = False
    timed_out: bool = False
    error: Optional[str] = None
    explanation: str = ""
    suggested_retry: Optional[str] = None
    fallback_reason: Optional[str] = None
    timeout_reason: Optional[str] = None
    time_col: str = ""
    value_col: str = ""
    horizon: int = 0
    n_points: int = 0
    frequency: str = "unknown"
    timings: ForecastTimings = field(default_factory=ForecastTimings)
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timings"] = self.timings.to_dict()
        return d
