from backend.agents.dataset_search_agent import dataset_search_agent
from backend.core.logger import get_logger
from backend.errors.error_types import DATASET_NOT_FOUND, DATASET_LOAD_FAILED
from backend.utils.dataset_loader import load_dataset

logger = get_logger(__name__)


def data_engineer_agent(state):
    logger.info(
        "Data engineer agent executing",
        extra={"action": "fetch_data", "question": state.get("question")},
    )

    if state.get("data") is not None:
        return state

    dataset_url = state.get("dataset_url")
    if not dataset_url:
        state = dataset_search_agent(state)
        dataset_url = state.get("dataset_url")

    if not dataset_url:
        if state.get("file_path"):
            return state

        state["error"] = "I could not locate a suitable dataset for this topic."
        state["error_type"] = DATASET_NOT_FOUND
        return state

    logger.info(
        "Loading dataset",
        extra={"action": "fetch_data", "dataset": dataset_url},
    )

    try:
        df = load_dataset(dataset_url)
        state["data"] = df
        state["dataset_url"] = dataset_url
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        state["dataset_topic"] = state.get("dataset_topic") or "dataset discovery"
        state["source"] = "dataset_discovery"
        state.pop("error", None)
        state["error_type"] = None
        logger.info(
            "Dataset loaded successfully",
            extra={"action": "fetch_data", "dataset": dataset_url, "rows": int(df.shape[0])},
        )
    except Exception as e:
        state["error"] = f"Dataset loading failed: {str(e)}"
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        logger.error(
            "Dataset loading failed",
            extra={"action": "fetch_data", "dataset": dataset_url, "error": str(e)},
        )

    return state
