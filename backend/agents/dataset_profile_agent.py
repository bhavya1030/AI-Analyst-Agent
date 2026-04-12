import pandas as pd


def dataset_profile_agent(state):

    df = state.get("data")

    if df is None:
        return state

    profile = {}

    # -----------------------------
    # BASIC STRUCTURE
    # -----------------------------

    profile["rows"] = df.shape[0]
    profile["columns"] = df.shape[1]

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(exclude="number").columns.tolist()

    profile["numeric_columns"] = numeric_cols
    profile["categorical_columns"] = categorical_cols

    # -----------------------------
    # TIME COLUMN DETECTION
    # -----------------------------

    time_columns = []

    for col in df.columns:

        col_lower = col.lower()

        if any(keyword in col_lower for keyword in ["date", "year", "time"]):
            time_columns.append(col)

    profile["time_columns"] = time_columns

    # -----------------------------
    # MISSING VALUES
    # -----------------------------

    missing = df.isnull().sum().to_dict()

    profile["missing_values"] = missing

    # -----------------------------
    # RECOMMENDED ANALYSES
    # -----------------------------

    recommendations = []

    if len(numeric_cols) >= 2:
        recommendations.append("correlation heatmap")

    if len(numeric_cols) >= 1:
        recommendations.append("distribution plot")

    if len(time_columns) >= 1:
        recommendations.append("trend analysis")

    if len(categorical_cols) >= 1:
        recommendations.append("category comparison")

    profile["recommended_analyses"] = recommendations

    # -----------------------------
    # SAVE INTO STATE
    # -----------------------------

    state["dataset_profile"] = profile

    return state
