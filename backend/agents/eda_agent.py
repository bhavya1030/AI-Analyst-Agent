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

    df = state.get("data")

    # SAFETY CHECK: dataset missing
    if df is None:
        state.setdefault("insights", [])
        state["insights"].append({
            "error": "No dataset available for EDA."
        })
        return state

    try:

        summary = {
            "rows": df.shape[0],
            "columns": list(df.columns),
            "missing_values": df.isnull().sum().to_dict(),
            "describe": df.describe(include="all").to_dict(),
        }

        summary = clean_for_json(summary)

        state.setdefault("insights", [])
        state["insights"].append(summary)

    except Exception as e:

        state.setdefault("insights", [])
        state["insights"].append({
            "error": f"EDA failed: {str(e)}"
        })

    return state