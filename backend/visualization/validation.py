"""Chart request validation and recommendation (Visualization v2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

import pandas as pd

from backend.visualization.inference import (
    CHART_TYPES,
    ChartSpec,
    ColumnRoles,
    infer_chart_spec,
    profile_columns,
)


@dataclass
class ValidationResult:
    ok: bool
    chart_type: str
    spec: Optional[ChartSpec] = None
    reason: str = ""
    recommended_type: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.spec is not None:
            d["spec"] = self.spec.to_dict()
        return d


# Human-readable labels for recommendations
_TYPE_LABELS = {
    "scatter": "Scatter Plot",
    "line": "Line Chart",
    "histogram": "Histogram",
    "pie": "Pie Chart",
    "heatmap": "Heatmap",
    "bar": "Bar Chart",
    "box": "Box Plot",
}


def recommend_chart_type(roles: ColumnRoles, *, requested: str | None = None) -> str:
    """Best chart type for the available column roles."""
    if roles.time and roles.numeric:
        return "line"
    if requested == "scatter" and len(roles.numeric) >= 2:
        return "scatter"
    if requested == "scatter" and roles.categorical and roles.numeric:
        return "bar"
    if len(roles.numeric) >= 2 and requested in {None, "heatmap", "correlation"}:
        if requested == "heatmap":
            return "heatmap"
    if roles.categorical and roles.numeric:
        return "bar"
    if len(roles.numeric) >= 2:
        return "scatter"
    if roles.numeric:
        return "histogram"
    if roles.categorical:
        return "pie"
    return "visualization"


def _type_requirements_met(chart_type: str, roles: ColumnRoles) -> tuple[bool, str]:
    if chart_type == "scatter":
        if len(roles.numeric) >= 2:
            return True, ""
        if roles.categorical and roles.numeric:
            return False, (
                "Scatter requires two numeric columns (numeric + numeric). "
                f"Found categorical columns {roles.categorical[:3]} and "
                f"numeric {roles.numeric[:3]}. Recommended: {_TYPE_LABELS['bar']}."
            )
        if len(roles.numeric) == 1:
            return False, (
                "Scatter requires two numeric columns; only one numeric column is available. "
                f"Recommended: {_TYPE_LABELS['histogram']}."
            )
        return False, "Scatter requires two numeric columns."

    if chart_type == "line":
        if (roles.time or len(roles.numeric) >= 1) and roles.numeric:
            return True, ""
        return False, "Line chart needs a time/order axis and a numeric value."

    if chart_type == "histogram":
        if roles.numeric:
            return True, ""
        return False, "Histogram requires a numeric column."

    if chart_type == "pie":
        if roles.categorical or roles.numeric:
            return True, ""
        return False, "Pie chart requires a categorical (or numeric) column."

    if chart_type == "heatmap":
        if len(roles.numeric) >= 2:
            return True, ""
        return False, (
            "Heatmap requires a numeric matrix (2+ numeric columns). "
            f"Recommended: {_TYPE_LABELS['histogram'] if roles.numeric else _TYPE_LABELS['bar']}."
        )

    if chart_type == "bar":
        if roles.categorical or roles.numeric:
            return True, ""
        return False, "Bar chart needs categorical or numeric columns."

    if chart_type == "box":
        if roles.numeric:
            return True, ""
        return False, "Box plot requires a numeric column."

    return True, ""


def validate_chart_request(
    df: pd.DataFrame,
    *,
    requested_type: str | None = None,
    question: str = "",
    time_columns: Sequence[str] | None = None,
    last_columns: Sequence[str] | None = None,
    x: str | None = None,
    y: str | None = None,
) -> ValidationResult:
    """
    Validate a chart request against dataframe dtypes.

    Always returns a usable ValidationResult. When the request is invalid,
    `ok=False` and `spec` contains a redirected/fallback ChartSpec when possible.
    """
    roles = profile_columns(df, time_columns=time_columns)
    req = (requested_type or "").lower().strip() or None
    if req and req not in CHART_TYPES:
        req = None

    # Explicit axis type check: scatter with Country + GDP
    if req == "scatter" and x and y and df is not None and not df.empty:
        x_num = x in roles.numeric
        y_num = y in roles.numeric
        if not (x_num and y_num):
            cat = x if not x_num else y
            num = y if y_num else (x if x_num else None)
            if not num:
                num = roles.numeric[0] if roles.numeric else None
            if not (cat in roles.categorical) and cat:
                # treat non-numeric as categorical for message
                pass
            reason = (
                f"Scatter requires numeric + numeric axes; "
                f"got '{x}' ({'numeric' if x_num else 'non-numeric'}) and "
                f"'{y}' ({'numeric' if y_num else 'non-numeric'}). "
                f"Recommended: {_TYPE_LABELS['bar']}."
            )
            # Force bar recommendation via inference with synthetic question
            spec = infer_chart_spec(
                df,
                question=f"bar chart of {num or y} by {cat or x}",
                time_columns=time_columns,
                preferred_type="bar",
                last_columns=last_columns,
            )
            spec.requested_type = "scatter"
            spec.redirected = True
            spec.redirect_reason = reason
            spec.recommended_type = "bar"
            return ValidationResult(
                ok=False,
                chart_type=spec.chart_type,
                spec=spec,
                reason=reason,
                recommended_type="bar",
                errors=[reason],
            )

    if req:
        met, why = _type_requirements_met(req, roles)
        if not met:
            spec = infer_chart_spec(
                df,
                question=question,
                time_columns=time_columns,
                preferred_type=req,
                last_columns=last_columns,
            )
            # infer_chart_spec already redirects
            return ValidationResult(
                ok=False,
                chart_type=spec.chart_type,
                spec=spec,
                reason=why or spec.redirect_reason,
                recommended_type=spec.recommended_type or recommend_chart_type(roles, requested=req),
                errors=[why or spec.redirect_reason],
                warnings=list(spec.notes),
            )

    spec = infer_chart_spec(
        df,
        question=question,
        time_columns=time_columns,
        preferred_type=req,
        last_columns=last_columns,
    )

    if spec.chart_type == "visualization" and spec.confidence <= 0:
        return ValidationResult(
            ok=False,
            chart_type="visualization",
            spec=spec,
            reason="No suitable columns for visualization.",
            errors=["no_suitable_columns"],
        )

    if spec.redirected:
        return ValidationResult(
            ok=False,
            chart_type=spec.chart_type,
            spec=spec,
            reason=spec.redirect_reason,
            recommended_type=spec.recommended_type,
            errors=[spec.redirect_reason] if spec.redirect_reason else [],
            warnings=list(spec.notes),
        )

    return ValidationResult(
        ok=True,
        chart_type=spec.chart_type,
        spec=spec,
        reason="ok",
        recommended_type=None,
        warnings=list(spec.notes),
    )
