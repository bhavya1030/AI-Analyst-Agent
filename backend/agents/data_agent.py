import pandas as pd


def data_agent(state):

    file_path = state.get("file_path", "data/sample.csv")

    df = pd.read_csv(file_path)

    state["data"] = df

    return state