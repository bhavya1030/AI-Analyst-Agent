import plotly.express as px
import plotly.figure_factory as ff

from backend.utils.column_semantic_mapper import map_column_reference
from backend.utils.json_safe import figure_to_json

try:
    from rapidfuzz import process
except ImportError:  # pragma: no cover
    process = None


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


def run_multi_viz_agent(state):
    df = state.get("data")
    if df is None:
        state["charts"] = []
        return state

    profile = state.get("dataset_profile", {})
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(exclude="number").columns.tolist()
    time_cols = profile.get("time_columns", [])

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
    return state


def viz_agent(state):
    try:
        df = state.get("data")
        question = (state.get("question") or "").lower()
        profile = state.get("dataset_profile", {})
        last_column = state.get("last_column_used")
        last_columns = state.get("last_columns_used") or []

        if df is None:
            state["chart"] = None
            state["chart_columns_used"] = []
            return state

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

        if "distribution" in question or "histogram" in question:
            col = _pick_column(question, numeric_cols, last_columns, last_column)
            if col is None:
                col = numeric_cols[0]
            fig = px.histogram(df, x=col)
            used_cols = [col]
            state["last_column_used"] = col
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
                fig = px.scatter(df, x=col_x, y=col_y)
                used_cols = [col_x, col_y]
                state["last_columns_used"] = used_cols
                state["last_column_used"] = col_y
                chart_type = "scatter"

        elif "correlation" in question or "heatmap" in question:
            if len(numeric_cols) >= 2:
                corr = df[numeric_cols].corr()
                fig = ff.create_annotated_heatmap(
                    z=corr.values,
                    x=list(corr.columns),
                    y=list(corr.columns),
                    colorscale="Viridis",
                )
                used_cols = numeric_cols
                chart_type = "heatmap"

        elif time_cols:
            time_col = time_cols[0]
            value_candidates = [col for col in numeric_cols if col != time_col]
            value_col = value_candidates[0] if value_candidates else numeric_cols[0]
            fig = px.line(df, x=time_col, y=value_col)
            used_cols = [time_col, value_col]
            state["last_columns_used"] = used_cols
            chart_type = "line"

        elif categorical_cols:
            category = categorical_cols[0]
            value_col = numeric_cols[0]
            fig = px.box(df, x=category, y=value_col)
            used_cols = [category, value_col]
            chart_type = "box"

        else:
            col = numeric_cols[0]
            fig = px.histogram(df, x=col)
            used_cols = [col]
            state["last_column_used"] = col
            chart_type = "histogram"

        if fig:
            state["chart"] = figure_to_json(fig)
            state["chart_columns_used"] = used_cols
            state["last_chart_type"] = chart_type
            state["rows"] = int(df.shape[0])
            state["columns"] = df.columns.tolist()
        else:
            state["chart"] = None
            state["chart_columns_used"] = []

        return state
    except Exception as exc:
        state["chart"] = None
        state["chart_columns_used"] = []
        state["error"] = f"Visualization failed: {exc}"
        return state
