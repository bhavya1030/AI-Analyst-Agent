from backend.errors.error_types import DATASET_LOAD_FAILED
from backend.utils.dataset_loader import load_dataset


def data_agent(state):

    file_path = state.get("file_path")

    if not file_path:
        state["error"] = "No dataset path provided."
        return state

    try:
        df = load_dataset(file_path)
    except Exception as exc:
        state["error"] = f"Dataset loading failed: {exc}"
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        return state

    state["data"] = df
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["dataset_url"] = None

    return state
