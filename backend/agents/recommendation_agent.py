def recommendation_agent(state):

    profile = state.get("dataset_profile")

    if not profile:
        state["recommended_next_steps"] = []
        return state

    recommendations = []

    numeric_cols = profile.get("numeric_columns", [])
    categorical_cols = profile.get("categorical_columns", [])
    time_cols = profile.get("time_columns", [])

    # -----------------------------
    # NUMERIC ANALYSIS
    # -----------------------------

    if len(numeric_cols) >= 2:
        recommendations.append(
            "Generate correlation heatmap between numeric variables"
        )

    if len(numeric_cols) >= 1:
        recommendations.append(
            f"Plot distribution of {numeric_cols[0]}"
        )

    # -----------------------------
    # TIME SERIES ANALYSIS
    # -----------------------------

    if len(time_cols) >= 1:
        recommendations.append(
            f"Run trend analysis over {time_cols[0]}"
        )

    # -----------------------------
    # CATEGORY COMPARISON
    # -----------------------------

    if len(categorical_cols) >= 1:
        recommendations.append(
            f"Compare values across {categorical_cols[0]}"
        )

    state["recommended_next_steps"] = recommendations

    return state
