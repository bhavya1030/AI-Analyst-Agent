def decision_agent(state):
    df = state["data"]

    if df.isnull().values.any():
        return "clean_data"

    return "skip_cleaning"