def insight_agent(state):

    insights = state.get("insights", [])

    if not insights:
        state["answer"] = "No dataset insights available."
        return state

    summary = insights[0]

    # SAFETY CHECK: summary may not contain expected keys
    if not isinstance(summary, dict):
        state["answer"] = "Invalid dataset summary."
        return state

    if "rows" not in summary:
        state["answer"] = summary.get(
            "error",
            "Dataset summary unavailable."
        )
        return state

    rows = summary.get("rows", 0)
    columns = summary.get("columns", [])
    missing = summary.get("missing_values", {})
    describe = summary.get("describe", {})

    text_output = []

    # Dataset structure
    text_output.append(
        f"Dataset contains {rows} rows and {len(columns)} columns."
    )

    # Missing values check
    if isinstance(missing, dict) and sum(missing.values()) == 0:
        text_output.append("No missing values detected.")
    else:
        text_output.append("Dataset contains missing values.")

    # Numeric column insights
    if isinstance(describe, dict):
        for col, stats in describe.items():

            if isinstance(stats, dict):

                if isinstance(stats.get("mean"), (int, float)):
                    mean_val = round(stats["mean"], 2)
                    text_output.append(f"Average {col} is {mean_val}.")

                if isinstance(stats.get("max"), (int, float)):
                    text_output.append(f"Maximum {col} is {stats['max']}.")

    state["answer"] = " ".join(text_output)

    return state