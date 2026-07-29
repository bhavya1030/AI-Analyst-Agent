"""Application-level checkpoint API (Phase 6).

Used after each completed turn and for resume / crash recovery / session switch.
Works with or without LangGraph auto-checkpoints.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from backend.core.logger import get_logger
from backend.graph.checkpoint_store import (
    delete_thread_checkpoints,
    ensure_checkpoint_schema,
    get_latest_checkpoint,
    list_checkpoints,
    save_checkpoint_row,
)
from backend.graph.state_codec import (
    build_dataset_ref,
    decode_state,
    encode_state,
    extract_planner_state,
    merge_checkpoint_into_state,
)
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)


class CheckpointService:
    """High-level checkpoint operations for sessions."""

    def __init__(self) -> None:
        ensure_checkpoint_schema()

    def save_turn_checkpoint(
        self,
        session_id: str,
        state: dict[str, Any],
        *,
        source: str = "turn",
        parent_checkpoint_id: str | None = None,
        status: str = "completed",
    ) -> dict[str, Any]:
        """Persist encoded graph + planner state after a successful turn."""
        encoded = encode_state(state)
        planner = extract_planner_state(state)
        dataset_ref = encoded.get("dataset_ref") or build_dataset_ref(state)
        checkpoint_id = str(uuid.uuid4())

        # Inherit parent = previous latest
        parent = parent_checkpoint_id
        if parent is None:
            prev = get_latest_checkpoint(session_id)
            if prev:
                parent = prev.get("checkpoint_id")

        row = save_checkpoint_row(
            thread_id=session_id,
            checkpoint_id=checkpoint_id,
            graph_state=encoded,
            planner_state=planner,
            dataset_ref=dataset_ref,
            parent_checkpoint_id=parent,
            source=source,
            status=status,
            mark_latest=True,
        )
        logger.info(
            "Turn checkpoint saved",
            extra={
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "source": source,
            },
        )
        return row

    def load_latest(
        self,
        session_id: str,
        *,
        reload_frames: bool = True,
    ) -> dict[str, Any] | None:
        """Load latest checkpoint and decode to runnable state."""
        row = get_latest_checkpoint(session_id)
        if not row:
            return None
        state = decode_state(row.get("graph_state") or {}, reload_frames=reload_frames)
        return {
            "checkpoint": sanitize_for_json(row),
            "graph_state": state,
            "planner_state": row.get("planner_state") or {},
            "dataset_ref": row.get("dataset_ref") or state.get("dataset_ref") or {},
            "resumable": True,
        }

    def resume_session(
        self,
        session_id: str,
        *,
        question: str | None = None,
        base_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Crash recovery / reopen: hydrate state from last completed checkpoint.

        Merges into base_state (fresh request shell) when provided.
        """
        loaded = self.load_latest(session_id, reload_frames=True)
        if not loaded:
            return {
                "session_id": session_id,
                "resumable": False,
                "graph_state": base_state or {},
                "planner_state": {},
                "checkpoint": None,
                "message": "No checkpoint found for session",
            }

        restored = loaded["graph_state"]
        if base_state:
            restored = merge_checkpoint_into_state(
                base_state, restored, prefer_checkpoint=True
            )
        if question:
            restored["question"] = question

        # Ensure planner can continue
        planner = loaded.get("planner_state") or {}
        if planner.get("plan") and not restored.get("plan"):
            restored["plan"] = planner["plan"]

        return {
            "session_id": session_id,
            "resumable": True,
            "graph_state": restored,
            "planner_state": planner,
            "dataset_ref": loaded.get("dataset_ref") or {},
            "checkpoint": loaded.get("checkpoint"),
            "message": "Checkpoint restored",
        }

    def switch_session(
        self,
        from_session_id: str | None,
        to_session_id: str,
        *,
        flush_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Switch active session: optionally flush from_session, then load to_session.

        Checkpoints for `from` should already exist after each turn; flush_state
        allows a final save before leaving.
        """
        if from_session_id and flush_state:
            try:
                self.save_turn_checkpoint(
                    from_session_id, flush_state, source="switch"
                )
            except Exception as exc:
                logger.warning(
                    "Failed to flush checkpoint on switch",
                    extra={"session_id": from_session_id, "error": str(exc)},
                )

        loaded = self.resume_session(to_session_id)
        loaded["from_session_id"] = from_session_id
        loaded["to_session_id"] = to_session_id
        loaded["switched"] = True
        return loaded

    def list_session_checkpoints(
        self, session_id: str, *, limit: int = 20
    ) -> dict[str, Any]:
        rows = list_checkpoints(session_id, limit=limit)
        # Strip large graph_state from list views
        items = []
        for r in rows:
            items.append(
                {
                    "checkpoint_id": r.get("checkpoint_id"),
                    "parent_checkpoint_id": r.get("parent_checkpoint_id"),
                    "source": r.get("source"),
                    "status": r.get("status"),
                    "is_latest": r.get("is_latest"),
                    "created_at": r.get("created_at"),
                    "dataset_ref": r.get("dataset_ref"),
                    "planner_state": r.get("planner_state"),
                    "has_graph_state": bool(r.get("graph_state")),
                }
            )
        return {
            "session_id": session_id,
            "total": len(items),
            "items": items,
        }

    def delete_session_checkpoints(self, session_id: str) -> int:
        return delete_thread_checkpoints(session_id)

    def has_checkpoint(self, session_id: str) -> bool:
        return get_latest_checkpoint(session_id) is not None


_service: CheckpointService | None = None
_lock = threading.Lock()


def get_checkpoint_service() -> CheckpointService:
    global _service
    with _lock:
        if _service is None:
            _service = CheckpointService()
        return _service
