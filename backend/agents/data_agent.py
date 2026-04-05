import pandas as pd
from pathlib import Path


def data_agent(state):
    file_path = Path(__file__).resolve().parents[2] / "data" / "sample.csv"

    df = pd.read_csv(file_path)

    state["data"] = df
    state["cleaned"] = False

    return state