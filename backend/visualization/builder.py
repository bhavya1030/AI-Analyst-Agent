"""Safe Plotly chart construction with fallbacks (Visualization v2)."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go

from backend.core.logger import get_logger
from backend.visualization.inference import ChartSpec, infer_chart_spec, profile_columns
from backend.visualization.validation import validate_chart_request

logger = get_logger(__name__)


def _prepare_xy(
    df: pd.DataFrame,
    x: Optional[str],
    y: Optional[str],
    *,
    dropna: bool = True,
) -> pd.DataFrame:
    cols = [c for c in (x, y) if c and c in df.columns]
    if not cols:
        return df.iloc[0:0].copy()
    out = df.loc[:, cols].copy()
    # Coerce object numerics
    for c in cols:
        if not pd.api.types.is_numeric_dtype(out[c]) and not pd.api.types.is_datetime64_any_dtype(out[c]):
            coerced = pd.to_numeric(out[c], errors="coerce")
            if coerced.notna().mean() >= 0.5:
                out[c] = coerced
    if dropna:
        out = out.dropna(how="any")
    return out


def _aggregate(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: Optional[str],
    aggregation: Optional[str],
    sort_by: Optional[str] = None,
    sort_ascending: bool = True,
    top_n: int = 30,
) -> pd.DataFrame:
    if group_col not in df.columns:
        return df.iloc[0:0].copy()
    work = df.copy()
    agg = (aggregation or "count").lower()
    if value_col and value_col in work.columns and agg != "count":
        # numeric coerce
        work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
        work = work.dropna(subset=[group_col, value_col])
        if agg == "mean":
            grouped = work.groupby(group_col, dropna=True)[value_col].mean().reset_index()
        elif agg == "median":
            grouped = work.groupby(group_col, dropna=True)[value_col].median().reset_index()
        else:
            grouped = work.groupby(group_col, dropna=True)[value_col].sum().reset_index()
        y_name = value_col
    else:
        work = work.dropna(subset=[group_col])
        grouped = work.groupby(group_col, dropna=True).size().reset_index(name="count")
        y_name = "count"

    sort_col = sort_by if sort_by in grouped.columns else y_name
    if sort_col in grouped.columns:
        grouped = grouped.sort_values(sort_col, ascending=sort_ascending)
    if len(grouped) > top_n:
        # keep top_n by absolute magnitude of y
        if y_name in grouped.columns:
            grouped = grouped.nlargest(top_n, y_name) if not sort_ascending else grouped.nsmallest(top_n, y_name)
            grouped = grouped.sort_values(y_name, ascending=sort_ascending)
    return grouped


def build_chart(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    """
    Build a Plotly figure for the given spec.
    Returns (fig, error). Never raises.
    """
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None, "empty_dataframe"
        ct = (spec.chart_type or "").lower()

        if ct == "scatter":
            return _build_scatter(df, spec)
        if ct == "line":
            return _build_line(df, spec)
        if ct == "histogram":
            return _build_histogram(df, spec)
        if ct == "pie":
            return _build_pie(df, spec)
        if ct == "heatmap":
            return _build_heatmap(df, spec)
        if ct == "bar":
            return _build_bar(df, spec)
        if ct == "box":
            return _build_box(df, spec)
        return None, f"unsupported_chart_type:{ct}"
    except Exception as exc:  # noqa: BLE001 — never crash
        logger.warning(
            "Chart build failed",
            extra={"chart_type": getattr(spec, "chart_type", None), "error": str(exc)},
        )
        return None, str(exc)


def _build_scatter(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    if not spec.x or not spec.y:
        return None, "scatter_missing_axes"
    plot_df = _prepare_xy(df, spec.x, spec.y)
    if plot_df.empty or len(plot_df) < 1:
        return None, "scatter_no_valid_rows"
    # Require numeric after coerce
    for c in (spec.x, spec.y):
        if not pd.api.types.is_numeric_dtype(plot_df[c]):
            return None, f"scatter_non_numeric:{c}"
    fig = px.scatter(plot_df, x=spec.x, y=spec.y, title=f"{spec.y} vs {spec.x}")
    return fig, None


def _build_line(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    if not spec.x or not spec.y:
        return None, "line_missing_axes"
    plot_df = _prepare_xy(df, spec.x, spec.y)
    if plot_df.empty:
        return None, "line_no_valid_rows"
    plot_df = plot_df.sort_values(spec.x)
    # Aggregate duplicates on x
    if plot_df[spec.x].duplicated().any():
        plot_df = (
            plot_df.groupby(spec.x, as_index=False)[spec.y]
            .mean()
            .sort_values(spec.x)
        )
    fig = px.line(plot_df, x=spec.x, y=spec.y, title=f"{spec.y} over {spec.x}")
    return fig, None


def _build_histogram(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    col = spec.x or (spec.columns[0] if spec.columns else None)
    if not col or col not in df.columns:
        return None, "histogram_missing_column"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return None, "histogram_no_valid_rows"
    plot_df = pd.DataFrame({col: s})
    fig = px.histogram(plot_df, x=col, title=f"Distribution of {col}")
    return fig, None


def _build_pie(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    names = spec.x or spec.group_by
    if not names or names not in df.columns:
        return None, "pie_missing_category"
    values = spec.y
    if values and values in df.columns:
        grouped = _aggregate(
            df,
            group_col=names,
            value_col=values,
            aggregation=spec.aggregation or "sum",
            sort_by=values,
            sort_ascending=False,
            top_n=12,
        )
        if grouped.empty:
            return None, "pie_no_valid_rows"
        fig = px.pie(
            grouped,
            names=names,
            values=values if values in grouped.columns else grouped.columns[-1],
            title=f"{values} by {names}",
        )
    else:
        grouped = _aggregate(
            df,
            group_col=names,
            value_col=None,
            aggregation="count",
            sort_ascending=False,
            top_n=12,
        )
        if grouped.empty:
            return None, "pie_no_valid_rows"
        fig = px.pie(grouped, names=names, values="count", title=f"Share of {names}")
    return fig, None


def _build_heatmap(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    cols = [c for c in (spec.columns or []) if c in df.columns]
    if len(cols) < 2:
        roles = profile_columns(df)
        cols = roles.numeric[:12]
    if len(cols) < 2:
        return None, "heatmap_need_2_numeric"
    num_df = df[cols].apply(pd.to_numeric, errors="coerce")
    # Drop columns that are all-NaN
    num_df = num_df.dropna(axis=1, how="all")
    if num_df.shape[1] < 2:
        return None, "heatmap_insufficient_numeric"
    corr = num_df.corr()
    # Replace NaN correlations with 0 for display stability
    z = corr.fillna(0).values
    try:
        fig = ff.create_annotated_heatmap(
            z=z,
            x=list(corr.columns.astype(str)),
            y=list(corr.columns.astype(str)),
            colorscale="Viridis",
            showscale=True,
        )
        fig.update_layout(title="Correlation heatmap")
    except Exception:
        fig = go.Figure(
            data=go.Heatmap(
                z=z,
                x=list(corr.columns.astype(str)),
                y=list(corr.columns.astype(str)),
                colorscale="Viridis",
            )
        )
        fig.update_layout(title="Correlation heatmap")
    return fig, None


def _build_bar(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    x = spec.x or spec.group_by
    y = spec.y
    if not x or x not in df.columns:
        return None, "bar_missing_category"
    grouped = _aggregate(
        df,
        group_col=x,
        value_col=y if y and y in df.columns else None,
        aggregation=spec.aggregation or ("sum" if y else "count"),
        sort_by=spec.sort_by or y,
        sort_ascending=spec.sort_ascending,
        top_n=40,
    )
    if grouped.empty:
        return None, "bar_no_valid_rows"
    y_col = y if y and y in grouped.columns else (
        "count" if "count" in grouped.columns else grouped.columns[-1]
    )
    fig = px.bar(grouped, x=x, y=y_col, title=f"{y_col} by {x}")
    return fig, None


def _build_box(df: pd.DataFrame, spec: ChartSpec) -> tuple[Optional[Any], Optional[str]]:
    if not spec.x or not spec.y:
        return None, "box_missing_axes"
    plot_df = df[[spec.x, spec.y]].copy()
    plot_df[spec.y] = pd.to_numeric(plot_df[spec.y], errors="coerce")
    plot_df = plot_df.dropna()
    if plot_df.empty:
        return None, "box_no_valid_rows"
    # Limit categories
    if plot_df[spec.x].nunique() > 25:
        top = plot_df[spec.x].value_counts().nlargest(25).index
        plot_df = plot_df[plot_df[spec.x].isin(top)]
    fig = px.box(plot_df, x=spec.x, y=spec.y, title=f"{spec.y} by {spec.x}")
    return fig, None


_FALLBACK_ORDER = ("histogram", "bar", "line", "scatter", "pie", "heatmap")


def build_chart_safe(
    df: pd.DataFrame,
    *,
    question: str = "",
    preferred_type: str | None = None,
    time_columns: list[str] | None = None,
    last_columns: list[str] | None = None,
    x: str | None = None,
    y: str | None = None,
) -> dict[str, Any]:
    """
    End-to-end safe chart pipeline:
      validate → build → fallback chain → never raises.

    Returns dict with keys: fig, spec, validation, error, fallback_used.
    """
    result: dict[str, Any] = {
        "fig": None,
        "spec": None,
        "validation": None,
        "error": None,
        "fallback_used": False,
        "chart_type": None,
    }
    try:
        validation = validate_chart_request(
            df,
            requested_type=preferred_type,
            question=question,
            time_columns=time_columns,
            last_columns=last_columns,
            x=x,
            y=y,
        )
        result["validation"] = validation
        spec = validation.spec
        if spec is None:
            spec = infer_chart_spec(
                df,
                question=question,
                time_columns=time_columns,
                preferred_type=preferred_type,
                last_columns=last_columns,
            )
        result["spec"] = spec

        fig, err = build_chart(df, spec)
        if fig is not None:
            result["fig"] = fig
            result["chart_type"] = spec.chart_type
            result["error"] = None
            result["fallback_used"] = bool(spec.redirected)
            return result

        # Fallback chain
        roles = profile_columns(df, time_columns=time_columns)
        tried = {spec.chart_type}
        for fb in _FALLBACK_ORDER:
            if fb in tried:
                continue
            if fb == "scatter" and len(roles.numeric) < 2:
                continue
            if fb == "heatmap" and len(roles.numeric) < 2:
                continue
            if fb == "histogram" and not roles.numeric:
                continue
            if fb in {"bar", "pie"} and not (roles.categorical or roles.numeric):
                continue
            fb_spec = infer_chart_spec(
                df,
                question=question,
                time_columns=time_columns,
                preferred_type=fb,
                last_columns=last_columns,
            )
            fig2, err2 = build_chart(df, fb_spec)
            tried.add(fb)
            if fig2 is not None:
                fb_spec.redirected = True
                fb_spec.redirect_reason = (
                    fb_spec.redirect_reason
                    or f"Primary chart failed ({err}); fell back to {fb}."
                )
                result["fig"] = fig2
                result["spec"] = fb_spec
                result["chart_type"] = fb_spec.chart_type
                result["error"] = None
                result["fallback_used"] = True
                return result
            err = err2 or err

        result["error"] = err or "chart_build_failed"
        result["chart_type"] = spec.chart_type if spec else None
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("build_chart_safe failed", extra={"error": str(exc)})
        result["error"] = str(exc)
        return result
