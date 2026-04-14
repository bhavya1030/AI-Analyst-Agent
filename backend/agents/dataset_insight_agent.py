def dataset_insight_agent(state):

    profile = state.get("dataset_profile")

    if not profile:
        state["dataset_explanation"] = []
        return state

    insights = []

    numeric_cols = profile.get("numeric_columns", [])
    categorical_cols = profile.get("categorical_columns", [])
    time_cols = profile.get("time_columns", [])

    if time_cols:
        insights.append(
            f"The dataset includes time-based structure using '{time_cols[0]}', suitable for trend analysis."
        )

    if len(numeric_cols) >= 2:
        insights.append(
            "Multiple numeric variables detected, enabling correlation analysis."
        )

    if categorical_cols:
        insights.append(
            f"Categorical grouping available via '{categorical_cols[0]}', enabling comparisons across categories."
        )

    if time_cols:
        workflow_hint = "Recommended workflow: trend analysis -> distribution analysis -> correlation study."
    elif categorical_cols:
        workflow_hint = "Recommended workflow: category comparison -> distribution analysis -> correlation study."
    else:
        workflow_hint = "Recommended workflow: distribution analysis -> correlation study."

    insights.append(workflow_hint)

    state["dataset_explanation"] = insights

    return state
