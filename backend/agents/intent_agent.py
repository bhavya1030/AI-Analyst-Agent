def intent_agent(state):

    question = state.get("question", "").lower()

    if any(word in question for word in ["plot", "chart", "graph", "distribution", "scatter", "bar"]):
        return "run_viz"

    if any(word in question for word in ["average", "mean", "max", "min", "count", "sum"]):
        return "run_qa"

    if any(word in question for word in ["summary", "describe", "structure", "columns"]):
        return "run_eda"

    if any(word in question for word in ["missing", "clean", "null"]):
        return "clean_data"

    return "run_qa"
