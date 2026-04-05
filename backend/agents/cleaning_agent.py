def cleaning_agent(state):
    df = state["data"]

    # simple cleaning logic
    df = df.dropna()

    state["data"] = df
    state["cleaned"] = True

    return state