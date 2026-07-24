"""LangGraph node: Dataset Retrieval Agent orchestration wrapper.

Calls backend.retrieval only. Does not acquire, clean, or analyze.
"""

from __future__ import annotations

from backend.core.logger import get_logger
from backend.retrieval import retrieve_dataset
from backend.utils.data_acquisition import DEFAULT_ACQUISITION_OPTIONS

logger = get_logger(__name__)


def dataset_retrieve_agent(state):
    """Resolve topic and run Dataset Retrieval Agent → state['retrieval_result']."""
    # Ensure we have a topic string for retrieval
    topic = (state.get("dataset_topic") or "").strip()
    if not topic:
        try:
            from backend.agents.dataset_topic_agent import dataset_topic_agent

            state = dataset_topic_agent(state)
            topic = (state.get("dataset_topic") or "").strip()
        except Exception as exc:
            logger.warning("Topic extraction failed in retrieve node", extra={"error": str(exc)})
            topic = (state.get("question") or "").strip()

    if not topic:
        state["retrieval_result"] = {
            "status": "NOT_FOUND",
            "reason": "No dataset topic could be determined from the request.",
            "topic": "",
            "next_action": "ASK_USER_UPLOAD",
        }
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["answer"] = (
            "I could not determine which dataset you need. "
            "Upload a file or ask about a clearer topic (e.g. India GDP, gold prices)."
        )
        state["stop"] = True
        return state

    force_new = bool(state.get("topic_mismatch") or state.get("force_reload_dataset"))
    # Session snapshot for SessionProvider (pre-reload binding)
    session_topic = state.get("session_dataset_topic") or (
        None if force_new else state.get("dataset_topic")
    )
    # When force_new, still pass previous session topic from dedicated field if any
    if force_new:
        session_topic = state.get("session_dataset_topic")

    request = {
        "topic": topic,
        "session_id": state.get("session_id"),
        "session_topic": session_topic,
        "session_dataset_url": None if force_new else state.get("dataset_url"),
        "session_local_path": state.get("local_path")
        or (None if force_new else state.get("file_path")),
        "session_dataset_id": state.get("dataset_id") or state.get("registry_id"),
        "has_active_data": bool(state.get("data") is not None and not force_new),
        "question": state.get("question"),
        "force_new_topic": force_new,
    }

    try:
        result = retrieve_dataset(request)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    except Exception as exc:
        logger.error("Retrieval agent failed", extra={"error": str(exc)})
        result_dict = {
            "status": "NOT_FOUND",
            "reason": f"Retrieval failed: {exc}",
            "topic": topic,
            "next_action": "ASK_USER_UPLOAD",
        }

    state["retrieval_result"] = result_dict
    state["dataset_topic"] = topic
    status = result_dict.get("status")
    logger.info(
        "Retrieve node complete",
        extra={"status": status, "topic": topic, "provider": result_dict.get("provider")},
    )

    if status in {"SEARCH_REQUIRED", "NOT_FOUND"}:
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["error"] = result_dict.get("reason") or "No dataset found."
        state["answer"] = (
            result_dict.get("reason")
            or f'I could not find a dataset for "{topic}". '
            "Please upload a CSV/Excel file or paste a direct download URL."
        )
        state["stop"] = True

    return state
