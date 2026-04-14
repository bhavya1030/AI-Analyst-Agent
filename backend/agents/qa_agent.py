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

    # fallback to last remembered column
    if last_column in columns:
        return last_column

    return None


def qa_agent(state):

    df = state.get("data")
    question = (state.get("question") or "").lower()
    last_column = state.get("last_column_used")

    if df is None:
        state["answer"] = "No dataset available."
        return state

    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if not numeric_cols:
        state["answer"] = "No numeric columns available."
        return state

    matched_col = best_column_match(
        question,
        numeric_cols,
        last_column
    )

    # -----------------------------
    # MEAN / AVERAGE
    # -----------------------------

    if "mean" in question or "average" in question:

        if matched_col:

            value = round(df[matched_col].mean(), 2)

            state["answer"] = f"Average {matched_col} = {value}"
            state["last_column_used"] = matched_col

        else:

            results = {
                col: round(df[col].mean(), 2)
                for col in numeric_cols
            }

            state["answer"] = f"Average values: {results}"

        return state


    # -----------------------------
    # MAX
    # -----------------------------

    if "max" in question:

        if matched_col:

            value = df[matched_col].max()

            state["answer"] = f"Maximum {matched_col} = {value}"
            state["last_column_used"] = matched_col

        else:

            results = {
                col: df[col].max()
                for col in numeric_cols
            }

            state["answer"] = f"Maximum values: {results}"

        return state


    # -----------------------------
    # MIN
    # -----------------------------

    if "min" in question:

        if matched_col:

            value = df[matched_col].min()

            state["answer"] = f"Minimum {matched_col} = {value}"
            state["last_column_used"] = matched_col

        else:

            results = {
                col: df[col].min()
                for col in numeric_cols
            }

            state["answer"] = f"Minimum values: {results}"

        return state


    # -----------------------------
    # MEDIAN
    # -----------------------------

    if "median" in question:

        if matched_col:

            value = df[matched_col].median()

            state["answer"] = f"Median {matched_col} = {value}"
            state["last_column_used"] = matched_col

        else:

            results = {
                col: df[col].median()
                for col in numeric_cols
            }

            state["answer"] = f"Median values: {results}"

        return state


    # -----------------------------
    # COUNT
    # -----------------------------

    if "count" in question:

        state["answer"] = f"Dataset contains {len(df)} rows."
        return state

    # -----------------------------
    # SUM
    # -----------------------------

    if "sum" in question:

        if matched_col:
            value = round(df[matched_col].sum(), 2)
            state["answer"] = f"Sum of {matched_col} = {value}"
            state["last_column_used"] = matched_col
        else:
            results = {
                col: round(df[col].sum(), 2)
                for col in numeric_cols
            }
            state["answer"] = f"Sum values: {results}"

        return state

    # -----------------------------
    # VARIANCE / STD
    # -----------------------------

    if "variance" in question or "std" in question:
        metric_name = "Variance" if "variance" in question else "Standard deviation"
        metric_func = "var" if "variance" in question else "std"

        if matched_col:
            value = round(getattr(df[matched_col], metric_func)(), 2)
            state["answer"] = f"{metric_name} of {matched_col} = {value}"
            state["last_column_used"] = matched_col
        else:
            results = {
                col: round(getattr(df[col], metric_func)(), 2)
                for col in numeric_cols
            }
            state["answer"] = f"{metric_name} values: {results}"

        return state


    # -----------------------------
    # DEFAULT FALLBACK
    # -----------------------------

    state["answer"] = df[numeric_cols].describe().to_string()

    return state
