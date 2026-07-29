"""LangGraph BaseCheckpointSaver backed by SQLite (Phase 6).

Encodes channel values through state_codec before persistence so DataFrames
never hit the database. Decoding reloads datasets from references.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.base.id import uuid6

from backend.core.logger import get_logger
from backend.graph.checkpoint_store import (
    delete_thread_checkpoints,
    ensure_checkpoint_schema,
    get_checkpoint,
    get_latest_checkpoint,
    list_checkpoints,
    save_checkpoint_row,
    save_writes,
)
from backend.graph.state_codec import (
    build_dataset_ref,
    decode_state,
    encode_state,
    encode_value,
    extract_planner_state,
)
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)


def _thread_id(config: RunnableConfig) -> str:
    return str(config.get("configurable", {}).get("thread_id") or "")


def _checkpoint_ns(config: RunnableConfig) -> str:
    return str(config.get("configurable", {}).get("checkpoint_ns") or "")


class SessionCheckpointer(BaseCheckpointSaver):
    """
    Durable checkpointer for analysis sessions.

    thread_id is expected to equal session_id.
    """

    def __init__(self) -> None:
        super().__init__()
        ensure_checkpoint_schema()
        self._lock = threading.RLock()

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = _thread_id(config)
        if not thread_id:
            return None
        ns = _checkpoint_ns(config)
        checkpoint_id = get_checkpoint_id(config)

        with self._lock:
            if checkpoint_id:
                row = get_checkpoint(thread_id, checkpoint_id, checkpoint_ns=ns)
            else:
                row = get_latest_checkpoint(thread_id, checkpoint_ns=ns)

        if not row:
            return None

        channel_values = decode_state(row.get("graph_state") or {}, reload_frames=True)
        checkpoint: Checkpoint = {
            "v": 1,
            "id": row["checkpoint_id"],
            "ts": str(row.get("created_at") or ""),
            "channel_values": channel_values,
            "channel_versions": row.get("channel_versions") or {},
            "versions_seen": row.get("versions_seen") or {},
            "updated_channels": None,
        }
        metadata = row.get("lg_metadata") or {
            "source": row.get("source") or "loop",
            "step": row.get("step") if row.get("step") is not None else 0,
        }
        parent_cfg = None
        if row.get("parent_checkpoint_id"):
            parent_cfg = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": ns,
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
            }
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": ns,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,  # type: ignore[arg-type]
            parent_config=parent_cfg,
            pending_writes=None,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if not config:
            return iter(())
        thread_id = _thread_id(config)
        ns = _checkpoint_ns(config)
        rows = list_checkpoints(thread_id, checkpoint_ns=ns, limit=limit or 20)
        before_id = get_checkpoint_id(before) if before else None
        for row in rows:
            if before_id and row["checkpoint_id"] >= before_id:
                continue
            meta = row.get("lg_metadata") or {}
            if filter and not all(meta.get(k) == v for k, v in filter.items()):
                continue
            tup = self.get_tuple(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": ns,
                        "checkpoint_id": row["checkpoint_id"],
                    }
                }
            )
            if tup:
                yield tup

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = _thread_id(config)
        ns = _checkpoint_ns(config)
        if not thread_id:
            raise ValueError("thread_id is required for SessionCheckpointer.put")

        c = dict(checkpoint)
        values = dict(c.pop("channel_values", {}) or {})
        # Encode full state dict safely
        encoded = encode_state(values)
        planner = extract_planner_state(values)
        dataset_ref = encoded.get("dataset_ref") or build_dataset_ref(values)

        parent_id = config.get("configurable", {}).get("checkpoint_id")
        ckpt_id = str(c.get("id") or uuid6())

        with self._lock:
            save_checkpoint_row(
                thread_id=thread_id,
                checkpoint_id=ckpt_id,
                checkpoint_ns=ns,
                parent_checkpoint_id=str(parent_id) if parent_id else None,
                graph_state=encoded,
                planner_state=planner,
                dataset_ref=dataset_ref,
                channel_versions=dict(c.get("channel_versions") or new_versions or {}),
                versions_seen=dict(c.get("versions_seen") or {}),
                lg_metadata=sanitize_for_json(dict(metadata or {})),
                lg_checkpoint_blob=json.dumps(
                    sanitize_for_json({**c, "channel_values": encoded})
                ),
                source=str((metadata or {}).get("source") or "langgraph"),
                step=(metadata or {}).get("step"),
                status="completed",
                mark_latest=True,
            )

        logger.info(
            "LangGraph checkpoint saved",
            extra={
                "thread_id": thread_id,
                "checkpoint_id": ckpt_id,
                "source": (metadata or {}).get("source"),
            },
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": ckpt_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = _thread_id(config)
        ns = _checkpoint_ns(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if not thread_id or not checkpoint_id:
            return
        # Encode write values (never store raw frames)
        safe_writes = [(str(ch), encode_value(val)) for ch, val in writes]
        with self._lock:
            save_writes(
                thread_id,
                str(checkpoint_id),
                safe_writes,
                task_id,
                checkpoint_ns=ns,
            )

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            delete_thread_checkpoints(thread_id)

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        # Not used by this product yet
        return

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        latest = get_latest_checkpoint(source_thread_id)
        if not latest:
            return
        new_id = str(uuid6())
        save_checkpoint_row(
            thread_id=target_thread_id,
            checkpoint_id=new_id,
            graph_state=latest.get("graph_state"),
            planner_state=latest.get("planner_state"),
            dataset_ref=latest.get("dataset_ref"),
            parent_checkpoint_id=None,
            channel_versions=latest.get("channel_versions"),
            versions_seen=latest.get("versions_seen"),
            lg_metadata={**(latest.get("lg_metadata") or {}), "source": "fork"},
            source="switch",
            status="completed",
            mark_latest=True,
        )


_checkpointer: SessionCheckpointer | None = None
_cp_lock = threading.Lock()


def get_session_checkpointer() -> SessionCheckpointer:
    global _checkpointer
    with _cp_lock:
        if _checkpointer is None:
            _checkpointer = SessionCheckpointer()
        return _checkpointer
