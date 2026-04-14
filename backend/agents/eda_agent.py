from backend.utils.json_safe import make_json_safe


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
            "rows": int(df.shape[0]),
            "columns": list(df.columns),
            "missing_values": df.isnull().sum().to_dict(),
            "describe": df.describe(include="all").to_dict(),
        }

        summary = make_json_safe(summary)

        state.setdefault("insights", [])
        state["insights"].append(summary)
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()

    except Exception as e:

        state.setdefault("insights", [])
        state["insights"].append({
            "error": f"EDA failed: {str(e)}"
        })

    return state
