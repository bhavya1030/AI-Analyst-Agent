def cleaning_agent(state):
    df = state.get("data")

    if df is None:
        state["answer"] = "No dataset available to clean."
        return state

    original_rows = len(df)
    df = df.dropna().copy()

    state["data"] = df
    state["cleaned"] = True
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state.setdefault("insights", []).append(
        {
            "cleaning_summary": {
                "rows_before": original_rows,
                "rows_after": int(df.shape[0]),
                "rows_removed": int(original_rows - len(df)),
            }
        }
    )

    return state
