def hypothesis_agent(state):
    profile = state.get("dataset_profile", {}) or {}
    hypotheses = []
    time_cols = profile.get("time_columns", [])
    numeric_cols = profile.get("numeric_columns", [])
    categorical_cols = profile.get("categorical_columns", [])
    topic = state.get("dataset_topic")
    forecast_target = state.get("last_forecast_target")

    if time_cols and numeric_cols:
        time_col = time_cols[0]
        hypotheses.append(
            f"Consider comparing {numeric_cols[0]} before and after the median {time_col} to evaluate shifts in trend."
        )

    if len(numeric_cols) >= 2:
        hypotheses.append(
            f"Validate whether {numeric_cols[0]} and {numeric_cols[1]} maintain a consistent correlation across different segments."
        )

    if categorical_cols and numeric_cols:
        hypotheses.append(
            f"Explore whether categories in {categorical_cols[0]} explain variation in {numeric_cols[0]}."
        )

    if topic:
        hypotheses.append(
            f"Investigate whether changes in {topic} correspond with wider economic or policy events."
        )

    if forecast_target:
        hypotheses.append(
            f"Confirm whether the forecast target {forecast_target} is stable across the most recent historical periods."
        )

    if not hypotheses:
        hypotheses.append(
            "Review the most important variables and check for structural breaks before drawing conclusions."
        )

    state["hypotheses"] = hypotheses
    return state
