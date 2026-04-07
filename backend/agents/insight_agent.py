def insight_agent(state):

    insights = state.get("insights", [])

    if not insights:
        state["answer"] = "No dataset insights available."
        return state

    summary = insights[0]

    rows = summary["rows"]
    columns = summary["columns"]
    missing = summary["missing_values"]
    describe = summary["describe"]

    text_output = []

    # Dataset structure
    text_output.append(f"Dataset contains {rows} rows and {len(columns)} columns.")

    # Missing values check
    if sum(missing.values()) == 0:
        text_output.append("No missing values detected.")
    else:
        text_output.append("Dataset contains missing values.")

    # Numeric column insights
    for col, stats in describe.items():
        if isinstance(stats.get("mean"), (int, float)):
            mean_val = round(stats["mean"], 2)
            text_output.append(f"Average {col} is {mean_val}.")

        if stats.get("max") is not None and isinstance(stats["max"], (int, float)):
            text_output.append(f"Maximum {col} is {stats['max']}.")

    state["answer"] = " ".join(text_output)

    return state