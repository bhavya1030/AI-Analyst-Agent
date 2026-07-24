"""LangGraph node: prepare local dataset for Data Engineer.

Branches on RetrievalResult:
  SESSION_HIT / REGISTRY_HIT (+ local file) → pass local_path
  API_HIT / INTERNET_HIT / STALE with URL → Acquisition → Intelligence → Learning
  failures → stop with user-facing error

Does not put download/EDA/viz logic into Retrieval/Acquisition modules.
"""

from __future__ import annotations

from pathlib import Path

from backend.core.logger import get_logger
from backend.utils.data_acquisition import CONNECT_SOURCES_HINT, DEFAULT_ACQUISITION_OPTIONS

logger = get_logger(__name__)


def dataset_prepare_agent(state):
    """Ensure state has local_path + dataset_metadata for Data Engineer."""
    if state.get("stop"):
        return state

    retrieval = state.get("retrieval_result") or {}
    status = retrieval.get("status") or ""
    topic = state.get("dataset_topic") or retrieval.get("topic") or "dataset"

    # Already have usable in-memory data and session hit — engineer will reuse
    if status == "SESSION_HIT" and state.get("data") is not None and not state.get("force_reload_dataset"):
        state["dataset_metadata"] = retrieval.get("metadata") or {
            "topic": topic,
            "source": "session",
        }
        state["local_path"] = (
            retrieval.get("local_path")
            or state.get("local_path")
            or state.get("file_path")
        )
        if retrieval.get("download_url"):
            state["dataset_url"] = retrieval.get("download_url")
        state["source"] = state.get("source") or "session"
        return state

    # Prefer existing local path when present and file exists
    local_path = retrieval.get("local_path") or state.get("local_path")
    if status in {"SESSION_HIT", "REGISTRY_HIT", "SEMANTIC_HIT"} and local_path and Path(str(local_path)).is_file():
        return _bind_local(state, local_path, retrieval, topic, source_label=status)

    # Registry/semantic hit with download_url only, or remote hits → acquire pipeline
    needs_acquire = status in {
        "API_HIT",
        "INTERNET_HIT",
        "STALE_REGISTRY_ENTRY",
        "REGISTRY_HIT",  # may only have URL
        "SEMANTIC_HIT",  # may only have URL
        "SESSION_HIT",  # may only have remote URL without in-memory data
    }
    download_url = retrieval.get("download_url") or (retrieval.get("metadata") or {}).get(
        "download_url"
    )

    if needs_acquire and download_url:
        return _acquire_profile_learn(state, retrieval, topic)

    if needs_acquire and local_path and Path(str(local_path)).is_file():
        return _bind_local(state, local_path, retrieval, topic, source_label=status)

    # Explicit user file path (upload) without going through retrieval hits
    if state.get("file_path") and Path(str(state["file_path"])).is_file():
        state["local_path"] = state["file_path"]
        state["dataset_metadata"] = {
            "topic": topic,
            "local_path": state["file_path"],
            "source": "user_upload",
            "source_type": "Upload",
        }
        state["source"] = "user_upload"
        return state

    # Failure: retrieval asked for user or nothing usable
    if status in {"SEARCH_REQUIRED", "NOT_FOUND"} or not download_url:
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["error"] = retrieval.get("reason") or "Dataset preparation failed."
        state["answer"] = (
            state.get("answer")
            or retrieval.get("reason")
            or f'No downloadable dataset available for "{topic}". {CONNECT_SOURCES_HINT}'
        )
        state["stop"] = True
        return state

    state["error"] = "Could not prepare a local dataset path."
    state["answer"] = state["error"] + " " + CONNECT_SOURCES_HINT
    state["needs_user_data"] = True
    state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
    state["stop"] = True
    return state


def _bind_local(state, local_path, retrieval, topic, source_label: str):
    state["local_path"] = str(local_path)
    meta = dict(retrieval.get("metadata") or {})
    meta.setdefault("topic", topic)
    meta.setdefault("local_path", str(local_path))
    if retrieval.get("dataset_id"):
        meta.setdefault("dataset_id", retrieval.get("dataset_id"))
        state["dataset_id"] = retrieval.get("dataset_id")
    if retrieval.get("download_url"):
        state["dataset_url"] = retrieval.get("download_url")
        meta.setdefault("download_url", retrieval.get("download_url"))
    state["dataset_metadata"] = meta
    state["source"] = source_label.lower()
    return state


def _acquire_profile_learn(state, retrieval, topic):
    from backend.acquisition import acquire_dataset
    from backend.intelligence import profile_dataset
    from backend.learning import learn_dataset

    try:
        acquisition = acquire_dataset(retrieval)
    except Exception as exc:
        logger.error("Acquisition raised", extra={"error": str(exc)})
        state["error"] = f"Acquisition failed: {exc}"
        state["answer"] = state["error"]
        state["acquisition_result"] = {"success": False, "errors": [str(exc)]}
        state["stop"] = True
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        return state

    acq_dict = acquisition.to_dict() if hasattr(acquisition, "to_dict") else dict(acquisition)
    state["acquisition_result"] = acq_dict

    if not acq_dict.get("success"):
        errors = acq_dict.get("errors") or ["Acquisition failed."]
        state["error"] = "; ".join(str(e) for e in errors)
        state["answer"] = f"Dataset download/acquisition failed: {state['error']}"
        state["stop"] = True
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        logger.warning("Acquisition failed", extra={"errors": errors})
        return state

    local_path = acq_dict.get("local_path")
    state["local_path"] = local_path
    state["dataset_id"] = acq_dict.get("dataset_id") or state.get("dataset_id")
    if acq_dict.get("source_url"):
        state["dataset_url"] = acq_dict.get("source_url")

    # Intelligence (structure only) — non-fatal
    profile_dict = None
    try:
        profile = profile_dataset(local_path)
        profile_dict = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
        state["dataset_intelligence"] = profile_dict
    except Exception as exc:
        logger.warning("Dataset intelligence failed; continuing", extra={"error": str(exc)})
        state["dataset_intelligence_error"] = str(exc)

    # Learning — non-fatal
    try:
        learning = learn_dataset(
            retrieval=retrieval,
            acquisition=acq_dict,
            profile=profile_dict,
        )
        learn_dict = learning.to_dict() if hasattr(learning, "to_dict") else dict(learning)
        state["learning_result"] = learn_dict
        if learn_dict.get("registry_id"):
            state["registry_id"] = learn_dict.get("registry_id")
            state["dataset_id"] = state.get("dataset_id") or learn_dict.get("registry_id")
    except Exception as exc:
        logger.warning("Dataset learning failed; continuing analysis", extra={"error": str(exc)})
        state["learning_error"] = str(exc)

    meta = dict(retrieval.get("metadata") or {})
    meta["topic"] = topic
    meta["local_path"] = local_path
    meta["download_url"] = acq_dict.get("source_url") or retrieval.get("download_url")
    meta["checksum"] = acq_dict.get("checksum")
    meta["file_format"] = acq_dict.get("detected_format")
    if profile_dict:
        meta["columns"] = profile_dict.get("column_names") or meta.get("columns")
        meta["row_count"] = profile_dict.get("row_count")
        meta["date_range"] = profile_dict.get("date_range")
        meta["domain"] = profile_dict.get("domain")
    if state.get("dataset_id"):
        meta["dataset_id"] = state["dataset_id"]
    state["dataset_metadata"] = meta
    state["source"] = retrieval.get("provider") or "acquisition"
    state["dataset_topic"] = topic
    return state
