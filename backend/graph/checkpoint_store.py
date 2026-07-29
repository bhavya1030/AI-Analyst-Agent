"""SQLAlchemy storage for graph / planner checkpoints (Phase 6)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON

from backend.core.logger import get_logger
from backend.db import Base, SessionLocal, engine

logger = get_logger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class GraphCheckpointRecord(Base):
    """One durable checkpoint snapshot for a session thread."""

    __tablename__ = "graph_checkpoints"

    id = Column(String(36), primary_key=True, default=_uuid)
    thread_id = Column(String(128), nullable=False, index=True)  # == session_id
    checkpoint_ns = Column(String(128), nullable=False, default="")
    checkpoint_id = Column(String(64), nullable=False)
    parent_checkpoint_id = Column(String(64), nullable=True)

    # Application-level safe payloads
    graph_state = Column(JSON, nullable=True)  # encoded Analyst state
    planner_state = Column(JSON, nullable=True)
    dataset_ref = Column(JSON, nullable=True)

    # LangGraph native bits (optional)
    channel_versions = Column(JSON, nullable=True)
    versions_seen = Column(JSON, nullable=True)
    lg_metadata = Column(JSON, nullable=True)
    lg_checkpoint_blob = Column(Text, nullable=True)  # full LG checkpoint JSON if needed

    source = Column(String(32), nullable=True)  # turn | langgraph | resume | switch
    step = Column(Integer, nullable=True)
    is_latest = Column(Boolean, nullable=False, default=True)
    status = Column(String(32), nullable=False, default="completed")  # completed|partial

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "thread_id", "checkpoint_ns", "checkpoint_id", name="uq_graph_ckpt"
        ),
        Index("ix_graph_ckpt_thread_latest", "thread_id", "is_latest"),
        Index("ix_graph_ckpt_thread_created", "thread_id", "created_at"),
    )


class GraphCheckpointWriteRecord(Base):
    """Optional intermediate LangGraph writes for crash recovery mid-step."""

    __tablename__ = "graph_checkpoint_writes"

    id = Column(String(36), primary_key=True, default=_uuid)
    thread_id = Column(String(128), nullable=False, index=True)
    checkpoint_ns = Column(String(128), nullable=False, default="")
    checkpoint_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False)
    idx = Column(Integer, nullable=False, default=0)
    channel = Column(String(128), nullable=True)
    value = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_graph_ckpt_writes_lookup",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
        ),
    )


def ensure_checkpoint_schema() -> None:
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        GraphCheckpointRecord.__table__.create(bind=engine, checkfirst=True)
        GraphCheckpointWriteRecord.__table__.create(bind=engine, checkfirst=True)
        _schema_ready = True
        logger.info("Graph checkpoint tables ready")


def save_checkpoint_row(
    *,
    thread_id: str,
    checkpoint_id: str,
    graph_state: dict[str, Any] | None,
    planner_state: dict[str, Any] | None = None,
    dataset_ref: dict[str, Any] | None = None,
    parent_checkpoint_id: str | None = None,
    checkpoint_ns: str = "",
    channel_versions: dict | None = None,
    versions_seen: dict | None = None,
    lg_metadata: dict | None = None,
    lg_checkpoint_blob: str | None = None,
    source: str = "turn",
    step: int | None = None,
    status: str = "completed",
    mark_latest: bool = True,
) -> dict[str, Any]:
    ensure_checkpoint_schema()
    db = SessionLocal()
    try:
        if mark_latest:
            db.query(GraphCheckpointRecord).filter(
                GraphCheckpointRecord.thread_id == thread_id,
                GraphCheckpointRecord.checkpoint_ns == (checkpoint_ns or ""),
                GraphCheckpointRecord.is_latest.is_(True),
            ).update({"is_latest": False}, synchronize_session=False)

        row = GraphCheckpointRecord(
            id=_uuid(),
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns or "",
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            graph_state=graph_state,
            planner_state=planner_state,
            dataset_ref=dataset_ref,
            channel_versions=channel_versions,
            versions_seen=versions_seen,
            lg_metadata=lg_metadata,
            lg_checkpoint_blob=lg_checkpoint_blob,
            source=source,
            step=step,
            is_latest=True if mark_latest else False,
            status=status,
            created_at=_utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to save graph checkpoint",
            extra={"thread_id": thread_id, "error": str(exc)},
        )
        raise
    finally:
        db.close()


def get_latest_checkpoint(
    thread_id: str, *, checkpoint_ns: str = ""
) -> dict[str, Any] | None:
    ensure_checkpoint_schema()
    db = SessionLocal()
    try:
        row = (
            db.query(GraphCheckpointRecord)
            .filter(
                GraphCheckpointRecord.thread_id == thread_id,
                GraphCheckpointRecord.checkpoint_ns == (checkpoint_ns or ""),
                GraphCheckpointRecord.is_latest.is_(True),
            )
            .order_by(GraphCheckpointRecord.created_at.desc())
            .first()
        )
        if row is None:
            # fallback: most recent by time
            row = (
                db.query(GraphCheckpointRecord)
                .filter(
                    GraphCheckpointRecord.thread_id == thread_id,
                    GraphCheckpointRecord.checkpoint_ns == (checkpoint_ns or ""),
                )
                .order_by(GraphCheckpointRecord.created_at.desc())
                .first()
            )
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def get_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    *,
    checkpoint_ns: str = "",
) -> dict[str, Any] | None:
    ensure_checkpoint_schema()
    db = SessionLocal()
    try:
        row = (
            db.query(GraphCheckpointRecord)
            .filter(
                GraphCheckpointRecord.thread_id == thread_id,
                GraphCheckpointRecord.checkpoint_ns == (checkpoint_ns or ""),
                GraphCheckpointRecord.checkpoint_id == checkpoint_id,
            )
            .first()
        )
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def list_checkpoints(
    thread_id: str,
    *,
    checkpoint_ns: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    ensure_checkpoint_schema()
    limit = max(1, min(int(limit or 20), 100))
    db = SessionLocal()
    try:
        rows = (
            db.query(GraphCheckpointRecord)
            .filter(
                GraphCheckpointRecord.thread_id == thread_id,
                GraphCheckpointRecord.checkpoint_ns == (checkpoint_ns or ""),
            )
            .order_by(GraphCheckpointRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


def delete_thread_checkpoints(thread_id: str) -> int:
    ensure_checkpoint_schema()
    db = SessionLocal()
    try:
        n = (
            db.query(GraphCheckpointRecord)
            .filter(GraphCheckpointRecord.thread_id == thread_id)
            .delete(synchronize_session=False)
        )
        db.query(GraphCheckpointWriteRecord).filter(
            GraphCheckpointWriteRecord.thread_id == thread_id
        ).delete(synchronize_session=False)
        db.commit()
        return int(n or 0)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Failed to delete thread checkpoints",
            extra={"thread_id": thread_id, "error": str(exc)},
        )
        return 0
    finally:
        db.close()


def save_writes(
    thread_id: str,
    checkpoint_id: str,
    writes: list[tuple[str, Any]],
    task_id: str,
    *,
    checkpoint_ns: str = "",
) -> None:
    ensure_checkpoint_schema()
    db = SessionLocal()
    try:
        from backend.graph.state_codec import encode_value

        for idx, (channel, value) in enumerate(writes):
            db.add(
                GraphCheckpointWriteRecord(
                    id=_uuid(),
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns or "",
                    checkpoint_id=checkpoint_id,
                    task_id=task_id,
                    idx=idx,
                    channel=str(channel),
                    value=encode_value(value),
                    created_at=_utcnow(),
                )
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug(
            "Checkpoint writes save failed",
            extra={"thread_id": thread_id, "error": str(exc)},
        )
    finally:
        db.close()


def _row_to_dict(row: GraphCheckpointRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "checkpoint_ns": row.checkpoint_ns or "",
        "checkpoint_id": row.checkpoint_id,
        "parent_checkpoint_id": row.parent_checkpoint_id,
        "graph_state": row.graph_state,
        "planner_state": row.planner_state,
        "dataset_ref": row.dataset_ref,
        "channel_versions": row.channel_versions,
        "versions_seen": row.versions_seen,
        "lg_metadata": row.lg_metadata,
        "source": row.source,
        "step": row.step,
        "is_latest": bool(row.is_latest),
        "status": row.status,
        "created_at": row.created_at.isoformat()
        if isinstance(row.created_at, datetime)
        else row.created_at,
    }
