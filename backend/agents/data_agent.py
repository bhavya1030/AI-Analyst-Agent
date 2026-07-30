from backend.core.logger import get_logger
from backend.errors.error_types import DATASET_LOAD_FAILED
from backend.metadata.models import is_placeholder_label
from backend.utils.data_acquisition import CONNECT_SOURCES_HINT, DEFAULT_ACQUISITION_OPTIONS
from backend.utils.dataset_loader import load_dataset
from backend.utils.dataset_resolver import looks_like_direct_url

logger = get_logger(__name__)


def data_agent(state):
    """Load a user-provided file path or direct URL (connected source)."""

    file_path = state.get("file_path") or state.get("dataset_url")

    if not file_path:
        state["error"] = "No dataset path provided."
        state["answer"] = (
            "No file or URL provided. Upload a dataset, paste a direct file URL, "
            "or ask about a public topic for open-data search."
        )
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["stop"] = True
        return state

    try:
        df = load_dataset(file_path)
    except Exception as exc:
        state["error"] = f"Dataset loading failed: {exc}"
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        state["answer"] = f"Could not load the provided source. {CONNECT_SOURCES_HINT}"
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["stop"] = True
        return state

    state["data"] = df
    state["last_dataset"] = df
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["data_ready"] = True
    if looks_like_direct_url(str(file_path)):
        state["dataset_url"] = str(file_path)
        state["source"] = "direct_url"
        if not str(state.get("local_path") or "").strip():
            state["local_path"] = None
    else:
        state["dataset_url"] = state.get("dataset_url")
        state["source"] = "user_upload"
        state["local_path"] = str(file_path)
        state["file_path"] = str(file_path)

    # Auto metadata: replace "user provided dataset" with e.g. "India GDP"
    try:
        from backend.metadata import generate_and_register_dataset_metadata

        generate_and_register_dataset_metadata(
            state,
            df=df,
            local_path=None if looks_like_direct_url(str(file_path)) else str(file_path),
            register=True,
        )
    except Exception as exc:
        logger.warning(
            "Auto metadata generation failed; using fallback topic",
            extra={"error": str(exc)},
        )
        if is_placeholder_label(state.get("dataset_topic")) or not state.get("dataset_topic"):
            try:
                from backend.metadata.topic_detection import topic_from_columns_and_values

                state["dataset_topic"] = topic_from_columns_and_values(
                    state.get("columns") or [],
                    filename=str(file_path),
                    question=state.get("question"),
                )
                state["dataset_name"] = state["dataset_topic"]
            except Exception:
                state["dataset_topic"] = state.get("dataset_topic") or "user provided dataset"

    if is_placeholder_label(state.get("dataset_topic")) or not state.get("dataset_topic"):
        state["dataset_topic"] = state.get("dataset_name") or "user provided dataset"
    return state
