import pandas as pd
import numpy as np


def clean_for_json(obj):
    """
    Recursively replace NaN/inf values with None
    so FastAPI JSON serialization doesn't crash.
    """
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    else:
        return obj


def eda_agent(state):
    df = state["data"]

    summary = {
        "rows": df.shape[0],
        "columns": list(df.columns),
        "missing_values": df.isnull().sum().to_dict(),
        "describe": df.describe(include="all").to_dict(),
    }

    summary = clean_for_json(summary)

    if "insights" not in state or state["insights"] is None:
        state["insights"] = []

    state["insights"].append(summary)

    return state