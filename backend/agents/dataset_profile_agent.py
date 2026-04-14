import pandas as pd


def _is_time_column(df, column_name):
    column = df[column_name]
    normalized_name = column_name.lower().replace("-", "_").replace(" ", "_")
    tokens = set(normalized_name.split("_"))

    if pd.api.types.is_datetime64_any_dtype(column):
        return True

    if {"date", "time", "timestamp"} & tokens:
        return True

    if "year" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        values = values[(values >= 1800) & (values <= 2100)]
        return len(values) >= 2 and values.nunique() >= 2

    if "month" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        return values.between(1, 12).all() if not values.empty else False

    if "day" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        return values.between(1, 31).all() if not values.empty else False

    return False


def dataset_profile_agent(state):

    df = state.get("data")

    if df is None:
        state["dataset_profile"] = {}
        return state

    profile = {}

    # -----------------------------
    # BASIC STRUCTURE
    # -----------------------------

    profile["rows"] = int(df.shape[0])
    profile["columns"] = int(df.shape[1])
    profile["column_names"] = df.columns.tolist()

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(exclude="number").columns.tolist()

    profile["numeric_columns"] = numeric_cols
    profile["categorical_columns"] = categorical_cols

    # -----------------------------
    # TIME COLUMN DETECTION
    # -----------------------------

    time_columns = []

    for col in df.columns:
        if _is_time_column(df, col):
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
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()

    return state
