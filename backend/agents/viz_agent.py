import plotly.express as px
import plotly.figure_factory as ff

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


def viz_agent(state):
    try:
        df = state.get("data")
        question = (state.get("question") or "").lower()

        profile = state.get("dataset_profile", {})

        last_column = state.get("last_column_used")
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

        if "distribution" in question or "histogram" in question:

            col = best_column_match(question, numeric_cols, last_column)

            if col is None:
                col = numeric_cols[0]

            fig = px.histogram(df, x=col)

            used_cols = [col]
            state["last_column_used"] = col

        elif "vs" in question:

            parts = question.split("vs")

            if len(parts) == 2 and len(numeric_cols) >= 2:

                col_x = best_column_match(parts[0], numeric_cols)
                col_y = best_column_match(parts[1], numeric_cols)

                if col_x is None:
                    col_x = numeric_cols[0]

                if col_y is None and len(numeric_cols) > 1:
                    col_y = numeric_cols[1]
                elif col_y is None:
                    col_y = numeric_cols[0]

                fig = px.scatter(df, x=col_x, y=col_y)

                used_cols = [col_x, col_y]

                state["last_columns_used"] = used_cols
                state["last_column_used"] = col_y

        elif "correlation" in question or "heatmap" in question:

            if len(numeric_cols) >= 2:

                corr = df[numeric_cols].corr()

                fig = ff.create_annotated_heatmap(
                    z=corr.values,
                    x=list(corr.columns),
                    y=list(corr.columns),
                    colorscale="Viridis"
                )

                used_cols = numeric_cols

        elif time_cols:

            time_col = time_cols[0]
            value_col = numeric_cols[-1]

            fig = px.line(df, x=time_col, y=value_col)

            used_cols = [time_col, value_col]

            state["last_columns_used"] = used_cols

        elif categorical_cols:

            category = categorical_cols[0]
            value_col = numeric_cols[0]

            fig = px.box(df, x=category, y=value_col)

            used_cols = [category, value_col]

        else:

            col = numeric_cols[0]

            fig = px.histogram(df, x=col)

            used_cols = [col]

            state["last_column_used"] = col

        if fig:

            state["chart"] = figure_to_json(fig)
            state["chart_columns_used"] = used_cols
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
