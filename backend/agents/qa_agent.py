from rapidfuzz import process


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


def qa_agent(state):

    df = state.get("data")
    question = state.get("question", "").lower()
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
    # DEFAULT FALLBACK
    # -----------------------------

    state["answer"] = df[numeric_cols].describe().to_string()

    return state