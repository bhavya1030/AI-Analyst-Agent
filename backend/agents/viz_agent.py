from rapidfuzz import process
import plotly.express as px
import plotly.figure_factory as ff


def best_column_match(text, columns, last_column=None):

    if not columns:
        return None

    match = process.extractOne(text, columns)

    if match and match[1] > 55:
        return match[0]

    # fallback to last remembered column
    if last_column in columns:
        return last_column

    return None


def extract_vs_columns(question, columns, last_columns=None):

    if "vs" not in question:
        return None, None

    parts = question.split("vs")

    if len(parts) != 2:
        return None, None

    left = parts[0].strip()
    right = parts[1].strip()

    col_x = best_column_match(left, columns)
    col_y = best_column_match(right, columns)

    # fallback to memory if needed
    if not col_x and last_columns:
        col_x = last_columns[0]

    if not col_y and last_columns and len(last_columns) > 1:
        col_y = last_columns[1]

    return col_x, col_y


def viz_agent(state):

    df = state.get("data")
    question = state.get("question", "").lower()

    last_column = state.get("last_column_used")
    last_columns = state.get("last_columns_used")

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

    # --------------------------------------------------
    # X vs Y DETECTION (SCATTER)
    # --------------------------------------------------

    x_col, y_col = extract_vs_columns(
        question,
        numeric_cols,
        last_columns
    )

    if x_col and y_col:

        fig = px.scatter(df, x=x_col, y=y_col)

        used_cols = [x_col, y_col]

        state["last_columns_used"] = used_cols
        state["last_column_used"] = y_col


    # --------------------------------------------------
    # TREND / TIME SERIES
    # --------------------------------------------------

    elif "trend" in question or "line" in question:

        y_col = best_column_match(
            question,
            numeric_cols,
            last_column
        )

        if not y_col and last_columns:
            y_col = last_columns[-1]

        if time_cols and y_col:

            fig = px.line(df, x=time_cols[0], y=y_col)

            used_cols = [time_cols[0], y_col]

            state["last_column_used"] = y_col


    # --------------------------------------------------
    # DISTRIBUTION
    # --------------------------------------------------

    elif "distribution" in question or "histogram" in question:

        col = best_column_match(
            question,
            numeric_cols,
            last_column
        )

        if col:

            fig = px.histogram(df, x=col)

            used_cols = [col]

            state["last_column_used"] = col


    # --------------------------------------------------
    # BAR CHART
    # --------------------------------------------------

    elif "bar" in question:

        col = best_column_match(
            question,
            numeric_cols,
            last_column
        )

        if col:

            fig = px.bar(df, y=col)

            used_cols = [col]

            state["last_column_used"] = col


    # --------------------------------------------------
    # BOX PLOT
    # --------------------------------------------------

    elif "box" in question:

        col = best_column_match(
            question,
            numeric_cols,
            last_column
        )

        if col:

            fig = px.box(df, y=col)

            used_cols = [col]

            state["last_column_used"] = col


    # --------------------------------------------------
    # CORRELATION HEATMAP
    # --------------------------------------------------

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

            state["last_columns_used"] = numeric_cols


    # --------------------------------------------------
    # DEFAULT FALLBACK TREND
    # --------------------------------------------------

    else:

        fallback_col = best_column_match(
            question,
            numeric_cols,
            last_column
        )

        if not fallback_col and last_columns:
            fallback_col = last_columns[-1]

        if time_cols and fallback_col:

            fig = px.line(df, x=time_cols[0], y=fallback_col)

            used_cols = [time_cols[0], fallback_col]

            state["last_column_used"] = fallback_col


    # --------------------------------------------------
    # FINALIZE OUTPUT
    # --------------------------------------------------

    if fig:

        state["chart"] = fig.to_json()
        state["chart_columns_used"] = used_cols

    else:

        state["chart"] = None
        state["chart_columns_used"] = None

    return state