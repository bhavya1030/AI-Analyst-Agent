"""Visualization v2 — inference, validation, safe chart building."""

from backend.visualization.builder import build_chart, build_chart_safe
from backend.visualization.inference import (
    ChartSpec,
    ColumnRoles,
    detect_requested_chart_type,
    infer_chart_spec,
    profile_columns,
)
from backend.visualization.validation import (
    ValidationResult,
    recommend_chart_type,
    validate_chart_request,
)

__all__ = [
    "ChartSpec",
    "ColumnRoles",
    "ValidationResult",
    "detect_requested_chart_type",
    "profile_columns",
    "infer_chart_spec",
    "validate_chart_request",
    "recommend_chart_type",
    "build_chart",
    "build_chart_safe",
]
