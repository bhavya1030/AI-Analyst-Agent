"""Safe serialization of Analyst / LangGraph state (Phase 6).

Rules:
  - Never persist pandas DataFrame / Series
  - Replace frames with dataset_ref {path, url, fingerprint, topic, id}
  - Reload frames via load_dataset when decoding
  - JSON-safe everything else via sanitize_for_json
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.core.logger import get_logger
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

# Keys that may hold DataFrames or other non-serializable payloads
_FRAME_KEYS = frozenset(
    {
        "data",
        "last_dataset",
        "dataframe",
        "df",
        "merged_dataframe",
        "frame",
        "frames",
    }
)


def build_dataset_ref(state: dict[str, Any]) -> dict[str, Any]:
    """Extract lightweight dataset pointer from state."""
    path = state.get("local_path") or state.get("file_path")
    url = state.get("dataset_url")
    # Prefer concrete file over remote when both exist
    if path and isinstance(path, str) and path.startswith(("http://", "https://")):
        url = url or path
        path = None
    return {
        "dataset_id": state.get("dataset_id") or state.get("registry_id"),
        "dataset_path": path if path and not str(path).startswith(("http://", "https://")) else None,
        "dataset_url": url,
        "dataset_topic": state.get("dataset_topic"),
        "dataset_fingerprint": state.get("dataset_fingerprint"),
        "source": state.get("source") or state.get("dataset_source"),
        "rows": state.get("rows"),
        "columns": list(state.get("columns") or [])[:200]
        if isinstance(state.get("columns"), list)
        else state.get("columns"),
    }


def encode_value(value: Any) -> Any:
    """Encode a single channel/value for persistence."""
    type_name = type(value).__name__
    if type_name in {"DataFrame", "Series"}:
        return None
    if isinstance(value, dict):
        return encode_state(value)
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    return sanitize_for_json(value)


def encode_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """
    Produce a JSON-safe state snapshot.

    DataFrames are dropped and replaced by dataset_ref on the top-level state.
    """
    if not state or not isinstance(state, dict):
        return {}

    out: dict[str, Any] = {}
    had_frame = False
    for key, value in state.items():
        if key in _FRAME_KEYS:
            type_name = type(value).__name__
            if type_name in {"DataFrame", "Series"} or value is not None:
                had_frame = had_frame or type_name in {"DataFrame", "Series"}
            continue
        type_name = type(value).__name__
        if type_name in {"DataFrame", "Series"}:
            had_frame = True
            continue
        out[key] = encode_value(value)

    ref = build_dataset_ref(state if isinstance(state, dict) else {})
    # Preserve any existing dataset_ref and merge
    existing_ref = state.get("dataset_ref") if isinstance(state.get("dataset_ref"), dict) else {}
    merged_ref = {**existing_ref, **{k: v for k, v in ref.items() if v is not None}}
    if had_frame or any(merged_ref.get(k) for k in ("dataset_path", "dataset_url", "dataset_id")):
        out["dataset_ref"] = sanitize_for_json(merged_ref)
        # Mirror convenience fields
        if merged_ref.get("dataset_path") and not out.get("file_path"):
            out["file_path"] = merged_ref["dataset_path"]
        if merged_ref.get("dataset_url") and not out.get("dataset_url"):
            out["dataset_url"] = merged_ref["dataset_url"]
        if merged_ref.get("dataset_topic") and not out.get("dataset_topic"):
            out["dataset_topic"] = merged_ref["dataset_topic"]
        if merged_ref.get("dataset_fingerprint") and not out.get("dataset_fingerprint"):
            out["dataset_fingerprint"] = merged_ref["dataset_fingerprint"]

    out["_codec_version"] = 1
    out["_encoded"] = True
    return sanitize_for_json(out) or {}


def extract_planner_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Planner-relevant slice for separate persistence."""
    if not state:
        return {}
    keys = (
        "plan",
        "last_intent",
        "last_operation",
        "intents",
        "question",
        "resolved_from_context",
        "context_subject",
        "topic_mismatch",
        "force_reload_dataset",
        "stop",
        "needs_user_data",
        "search_queries",
        "dataset_discovery",
    )
    return sanitize_for_json({k: state.get(k) for k in keys if k in state}) or {}


def decode_state(
    encoded: dict[str, Any] | None,
    *,
    reload_frames: bool = True,
) -> dict[str, Any]:
    """
    Restore a state dict from encoded form.

    When reload_frames=True, attempts to load DataFrame into data/last_dataset
    from dataset_ref path/url.
    """
    if not encoded or not isinstance(encoded, dict):
        return {}

    state = deepcopy(encoded)
    state.pop("_codec_version", None)
    state.pop("_encoded", None)

    ref = state.get("dataset_ref") if isinstance(state.get("dataset_ref"), dict) else {}
    # Ensure path/url fields exist for agents
    if ref.get("dataset_path") and not state.get("file_path"):
        state["file_path"] = ref["dataset_path"]
    if ref.get("dataset_url") and not state.get("dataset_url"):
        state["dataset_url"] = ref["dataset_url"]
    if ref.get("dataset_topic") and not state.get("dataset_topic"):
        state["dataset_topic"] = ref["dataset_topic"]
    if ref.get("dataset_id") and not state.get("dataset_id"):
        state["dataset_id"] = ref["dataset_id"]
    if ref.get("dataset_fingerprint") and not state.get("dataset_fingerprint"):
        state["dataset_fingerprint"] = ref["dataset_fingerprint"]

    state["data"] = None
    state["last_dataset"] = None

    if reload_frames:
        frame = _reload_frame(ref, state)
        if frame is not None:
            state["data"] = frame
            state["last_dataset"] = frame
            state["has_active_dataset"] = True
            try:
                state["rows"] = int(frame.shape[0])
                state["columns"] = frame.columns.tolist()
            except Exception:
                pass
        else:
            state["has_active_dataset"] = bool(
                state.get("file_path") or state.get("dataset_url")
            )

    return state


def _reload_frame(ref: dict[str, Any], state: dict[str, Any]):
    path = ref.get("dataset_path") or state.get("file_path") or state.get("local_path")
    url = ref.get("dataset_url") or state.get("dataset_url")
    candidates = []
    if path and not str(path).startswith(("http://", "https://")):
        candidates.append(str(path))
    if url:
        candidates.append(str(url))
    if not candidates:
        return None

    from backend.utils.dataset_loader import load_dataset

    for reference in candidates:
        try:
            df = load_dataset(reference)
            logger.info(
                "Dataset reloaded from checkpoint ref",
                extra={"dataset": reference},
            )
            return df
        except Exception as exc:
            logger.warning(
                "Checkpoint dataset reload failed",
                extra={"dataset": reference, "error": str(exc)},
            )
    return None


def merge_checkpoint_into_state(
    base: dict[str, Any],
    checkpoint_state: dict[str, Any],
    *,
    prefer_checkpoint: bool = True,
) -> dict[str, Any]:
    """
    Merge restored checkpoint fields into a freshly built request state.

    Fresh request fields (question, file_path override, topic_mismatch) win when
    prefer_checkpoint is False for those keys.
    """
    out = dict(base or {})
    cp = dict(checkpoint_state or {})

    request_keys = {
        "question",
        "topic_mismatch",
        "force_reload_dataset",
        "file_path",  # explicit upload this turn
    }

    for key, value in cp.items():
        if key in _FRAME_KEYS:
            continue
        if key in request_keys and key in out and out.get(key) not in (None, "", [], {}):
            # Keep request value
            continue
        if prefer_checkpoint or key not in out or out.get(key) in (None, "", [], {}):
            out[key] = value

    # Always take reloaded frames from checkpoint if present
    if cp.get("data") is not None and not out.get("topic_mismatch"):
        out["data"] = cp["data"]
        out["last_dataset"] = cp.get("last_dataset", cp["data"])
        out["has_active_dataset"] = True

    return out
