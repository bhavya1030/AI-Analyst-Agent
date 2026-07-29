import hashlib

import plotly.express as px
import plotly.figure_factory as ff

from backend.cache.analysis_cache import KIND_CHART, get_analysis_cache
from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.core.logger import get_logger
from backend.errors.error_types import VISUALIZATION_FAILED
from backend.utils.column_semantic_mapper import map_column_reference
from backend.utils.json_safe import figure_to_json

try:
    from rapidfuzz import process
except ImportError:  # pragma: no cover
    process = None

logger = get_logger(__name__)


def best_column_match(text, columns, last_column=None):
    if not columns:
        return None

    if process is not None:
        match = process.extractOne(text, columns)
    else:
        match = None

    if match and match[1] > 55:
        return match[0]

    if last_column in columns:
        return last_column

    return None


def _pick_column(reference, columns, last_columns, last_column=None):
    mapped = map_column_reference(reference, columns, last_columns)
    if mapped:
        return mapped
    return best_column_match(reference, columns, last_column)


def _serialize_chart(fig, chart_type, used_cols):
    return {
        "type": chart_type,
        "figure": figure_to_json(fig),
        "columns_used": used_cols,
    }


def _question_sig(question: str) -> str:
    normalized = " ".join((question or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _chart_params(
    *,
    mode: str,
    chart_type: str,
    columns: list[str],
    question: str = "",
) -> dict:
    return {
        "mode": mode,
        "chart_type": chart_type,
        "columns": sorted(str(c) for c in (columns or [])),
        "question_sig": _question_sig(question) if mode == "single" else "multi",
    }


def _apply_cached_charts(state, payload: dict, *, multi: bool) -> dict:
    if multi:
        charts = payload.get("charts") or []
        state["charts"] = charts
        state["chart"] = charts[0]["figure"] if charts else None
        state["chart_columns_used"] = list(payload.get("chart_columns_used") or [])
        state["last_chart_type"] = payload.get("last_chart_type") or "multi"
        state["last_columns_used"] = list(
            payload.get("last_columns_used") or state["chart_columns_used"]
        )
    else:
        state["chart"] = payload.get("chart")
        state["chart_columns_used"] = list(payload.get("chart_columns_used") or [])
        state["last_chart_type"] = payload.get("last_chart_type") or "visualization"
        if payload.get("last_column_used") is not None:
            state["last_column_used"] = payload.get("last_column_used")
        if payload.get("last_columns_used") is not None:
            state["last_columns_used"] = list(payload.get("last_columns_used") or [])
        # Keep charts list in sync for session persistence
        if state.get("chart") and not state.get("charts"):
            state["charts"] = [
                {
                    "type": state.get("last_chart_type") or "visualization",
                    "figure": state["chart"],
                    "columns_used": state.get("chart_columns_used") or [],
                }
            ]
    state["chart_from_cache"] = True
    return state


def run_multi_viz_agent(state):
    df = state.get("data")
    if df is None:
        state["charts"] = []
        return state

    reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
    fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
        df, reference
    )
    state["dataset_fingerprint"] = fingerprint

    profile = state.get("dataset_profile", {})
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(exclude="number").columns.tolist()
    time_cols = profile.get("time_columns", [])

    # Params are deterministic for multi mode (same profile columns → same charts)
    preview_cols: list[str] = []
    if time_cols and numeric_cols:
        time_col = time_cols[0]
        value_candidates = [col for col in numeric_cols if col != time_col]
        value_col = value_candidates[0] if value_candidates else numeric_cols[0]
        preview_cols.extend([time_col, value_col])
    if numeric_cols:
        preview_cols.append(numeric_cols[0])
    if len(numeric_cols) >= 2:
        preview_cols.extend(numeric_cols)
    if categorical_cols and numeric_cols:
        preview_cols.extend([categorical_cols[0], numeric_cols[0]])

    params = _chart_params(
        mode="multi",
        chart_type="multi",
        columns=list(dict.fromkeys(preview_cols)),
    )
    cached = get_analysis_cache().get(KIND_CHART, fingerprint, params)
    if cached is not None:
        _apply_cached_charts(state, cached, multi=True)
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        logger.info(
            "Multi visualization served from durable cache",
            extra={
                "action": "run_multi_viz",
                "dataset": reference,
                "fingerprint": fingerprint[:16],
                "chart_count": len(state.get("charts") or []),
            },
        )
        return state

    charts = []
    used_columns = []

    if time_cols and numeric_cols:
        time_col = time_cols[0]
        value_candidates = [col for col in numeric_cols if col != time_col]
        value_col = value_candidates[0] if value_candidates else numeric_cols[0]
        fig = px.line(df, x=time_col, y=value_col)
        charts.append(_serialize_chart(fig, "line", [time_col, value_col]))
        used_columns.extend([time_col, value_col])

    if numeric_cols:
        hist_col = numeric_cols[0]
        fig = px.histogram(df, x=hist_col)
        charts.append(_serialize_chart(fig, "histogram", [hist_col]))
        used_columns.append(hist_col)

    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr()
        fig = ff.create_annotated_heatmap(
            z=corr.values,
            x=list(corr.columns),
            y=list(corr.columns),
            colorscale="Viridis",
        )
        charts.append(_serialize_chart(fig, "heatmap", numeric_cols))
        used_columns.extend(numeric_cols)

    if categorical_cols and numeric_cols:
        category = categorical_cols[0]
        value_col = numeric_cols[0]
        fig = px.box(df, x=category, y=value_col)
        charts.append(_serialize_chart(fig, "box", [category, value_col]))
        used_columns.extend([category, value_col])

    state["charts"] = charts
    state["chart"] = charts[0]["figure"] if charts else None
    state["chart_columns_used"] = list(dict.fromkeys(used_columns))
    state["last_chart_type"] = "multi"
    state["last_columns_used"] = state["chart_columns_used"]
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["chart_from_cache"] = False

    payload = {
        "charts": charts,
        "chart_columns_used": state["chart_columns_used"],
        "last_chart_type": "multi",
        "last_columns_used": state["last_columns_used"],
    }
    get_analysis_cache().put(KIND_CHART, fingerprint, payload, params)

    logger.info(
        "Multi visualization generated and cached",
        extra={
            "action": "run_multi_viz",
            "dataset": reference,
            "fingerprint": fingerprint[:16],
            "chart_count": len(charts),
        },
    )
    return state


def viz_agent(state):
    try:
        df = state.get("data")
        question = (state.get("question") or "").lower()
        profile = state.get("dataset_profile", {})
        last_column = state.get("last_column_used")
        last_columns = state.get("last_columns_used") or []
        deep_mode = "deeply" in question or state.get("last_operation") == "deep_analysis"

        if df is None:
            state["chart"] = None
            state["chart_columns_used"] = []
            state["chart_error"] = "No data available for visualization."
            state["error_type"] = VISUALIZATION_FAILED
            return state

        if deep_mode:
            return run_multi_viz_agent(state)

        reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
        fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
            df, reference
        )
        state["dataset_fingerprint"] = fingerprint

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        categorical_cols = df.select_dtypes(exclude="number").columns.tolist()
        time_cols = profile.get("time_columns", [])

        if not numeric_cols:
            state["chart"] = None
            state["chart_columns_used"] = []
            return state

        fig = None
        used_cols = []
        chart_type = "visualization"
        last_column_used = None
        last_columns_used = None

        if "distribution" in question or "histogram" in question:
            col = _pick_column(question, numeric_cols, last_columns, last_column)
            if col is None:
                col = numeric_cols[0]
            used_cols = [col]
            last_column_used = col
            chart_type = "histogram"

        elif "vs" in question:
            parts = question.split("vs")
            if len(parts) == 2 and len(numeric_cols) >= 2:
                col_x = _pick_column(parts[0], numeric_cols, last_columns, last_column)
                col_y = _pick_column(parts[1], numeric_cols, last_columns, last_column)
                if col_x is None:
                    col_x = numeric_cols[0]
                if col_y is None:
                    col_y = numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
                used_cols = [col_x, col_y]
                last_columns_used = used_cols
                last_column_used = col_y
                chart_type = "scatter"

        elif "correlation" in question or "heatmap" in question:
            if len(numeric_cols) >= 2:
                used_cols = numeric_cols
                chart_type = "heatmap"

        elif time_cols:
            time_col = time_cols[0]
            value_candidates = [col for col in numeric_cols if col != time_col]
            value_col = value_candidates[0] if value_candidates else numeric_cols[0]
            used_cols = [time_col, value_col]
            last_columns_used = used_cols
            chart_type = "line"

        elif categorical_cols:
            category = categorical_cols[0]
            value_col = numeric_cols[0]
            used_cols = [category, value_col]
            chart_type = "box"

        else:
            col = numeric_cols[0]
            used_cols = [col]
            last_column_used = col
            chart_type = "histogram"

        params = _chart_params(
            mode="single",
            chart_type=chart_type,
            columns=used_cols,
            question=question,
        )
        cached = get_analysis_cache().get(KIND_CHART, fingerprint, params)
        if cached is not None:
            _apply_cached_charts(state, cached, multi=False)
            state["rows"] = int(df.shape[0])
            state["columns"] = df.columns.tolist()
            logger.info(
                "Visualization served from durable cache",
                extra={
                    "action": "run_viz",
                    "dataset": reference,
                    "fingerprint": fingerprint[:16],
                    "chart_type": chart_type,
                    "columns": used_cols,
                },
            )
            return state

        # Compute figure only on cache miss
        if chart_type == "histogram":
            fig = px.histogram(df, x=used_cols[0])
        elif chart_type == "scatter":
            fig = px.scatter(df, x=used_cols[0], y=used_cols[1])
        elif chart_type == "heatmap":
            corr = df[numeric_cols].corr()
            fig = ff.create_annotated_heatmap(
                z=corr.values,
                x=list(corr.columns),
                y=list(corr.columns),
                colorscale="Viridis",
            )
        elif chart_type == "line":
            fig = px.line(df, x=used_cols[0], y=used_cols[1])
        elif chart_type == "box":
            fig = px.box(df, x=used_cols[0], y=used_cols[1])

        if fig:
            chart_json = fig.to_plotly_json()
            state["chart"] = chart_json
            state["chart_columns_used"] = used_cols
            state["last_chart_type"] = chart_type
            if last_column_used is not None:
                state["last_column_used"] = last_column_used
            if last_columns_used is not None:
                state["last_columns_used"] = last_columns_used
            state["rows"] = int(df.shape[0])
            state["columns"] = df.columns.tolist()
            state["chart_from_cache"] = False
            state["charts"] = [
                {
                    "type": chart_type,
                    "figure": chart_json,
                    "columns_used": used_cols,
                }
            ]

            payload = {
                "chart": chart_json,
                "chart_columns_used": used_cols,
                "last_chart_type": chart_type,
                "last_column_used": last_column_used,
                "last_columns_used": last_columns_used,
            }
            get_analysis_cache().put(KIND_CHART, fingerprint, payload, params)

            logger.info(
                "Visualization generated and cached",
                extra={
                    "action": "run_viz",
                    "dataset": reference,
                    "fingerprint": fingerprint[:16],
                    "chart_type": chart_type,
                    "columns": used_cols,
                },
            )
        else:
            state["chart"] = None
            state["chart_columns_used"] = []

        return state
    except Exception as exc:
        state["chart"] = None
        state["chart_columns_used"] = []
        state["chart_error"] = f"Visualization failed: {exc}"
        state["error_type"] = VISUALIZATION_FAILED
        logger.error(
            "Visualization failed",
            extra={"action": "run_viz", "error": str(exc)},
        )
        return state
