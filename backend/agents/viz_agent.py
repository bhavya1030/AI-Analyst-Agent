import plotly.express as px
import plotly.figure_factory as ff


def viz_agent(state):

    df = state.get("data")
    question = state.get("question", "").lower()

    if df is None:
        state["chart"] = None
        return state

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    all_cols = df.columns.tolist()

    time_cols = [
        col for col in all_cols
        if "date" in col.lower()
        or "year" in col.lower()
        or "time" in col.lower()
    ]

    fig = None
    used_cols = []

    # TREND / LINE PLOT (time-series detection)
    if "trend" in question or "line" in question:

        if time_cols and numeric_cols:

            x_col = time_cols[0]
            y_col = numeric_cols[0]

            fig = px.line(df, x=x_col, y=y_col)

            used_cols = [x_col, y_col]

    # SCATTER
    elif "scatter" in question or "vs" in question:

        if len(numeric_cols) >= 2:

            x_col = numeric_cols[0]
            y_col = numeric_cols[1]

            fig = px.scatter(df, x=x_col, y=y_col)

            used_cols = [x_col, y_col]

    # HISTOGRAM
    elif "distribution" in question:

        if numeric_cols:

            fig = px.histogram(df, x=numeric_cols[0])

            used_cols = [numeric_cols[0]]

    # CORRELATION HEATMAP
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

    # DEFAULT TREND FALLBACK
    else:

        if time_cols and numeric_cols:

            fig = px.line(df, x=time_cols[0], y=numeric_cols[0])

            used_cols = [time_cols[0], numeric_cols[0]]

    if fig:

        state["chart"] = fig.to_json()
        state["chart_columns_used"] = used_cols

    else:

        state["chart"] = None
        state["chart_columns_used"] = None

    return state