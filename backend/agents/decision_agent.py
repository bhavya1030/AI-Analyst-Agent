def decision_agent(state):
    df = state["data"]
    question = state.get("question", "").lower()

    # Check if dataset needs cleaning
    if df.isnull().values.any():
        return "clean_data"

    # Route visualization questions
    if any(word in question for word in ["plot", "chart", "graph", "distribution", "scatter", "bar"]):
        return "run_viz"

    return "run_eda"