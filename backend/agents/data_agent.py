import pandas as pd


def data_agent(state):

    file_path = state.get("file_path")

    if not file_path:
        state["error"] = "No dataset path provided."
        return state

    df = pd.read_csv(file_path)

    state["data"] = df

    return state
