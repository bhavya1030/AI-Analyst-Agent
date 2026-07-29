"""Durable store for Level-2 / Level-3 memory (Phase 5).

L1 is derived from session_messages.
L4 is read from learned_datasets + dataset (not owned here).
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON

from backend.core.logger import get_logger
from backend.db import Base, SessionLocal, engine
from backend.memory.hierarchy_models import DatasetMemory, SessionMemory

logger = get_logger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class DatasetMemoryRecord(Base):
    """Cross-session memory keyed by dataset identity (fingerprint / topic+url)."""

    __tablename__ = "dataset_memory"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(128), nullable=False, default="anonymous", index=True)
    dataset_key = Column(String(128), nullable=False, index=True)
    dataset_fingerprint = Column(String(64), nullable=True, index=True)
    dataset_topic = Column(String(512), nullable=True)
    dataset_url = Column(String(2048), nullable=True)
    dataset_path = Column(String(2048), nullable=True)
    dataset_id = Column(String(128), nullable=True)

    columns_frequently_used = Column(JSON, nullable=True)
    successful_chart_types = Column(JSON, nullable=True)
    last_forecast_targets = Column(JSON, nullable=True)
    insights_digest = Column(JSON, nullable=True)
    last_session_ids = Column(JSON, nullable=True)
    last_profile_summary = Column(JSON, nullable=True)
    analysis_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "dataset_key", name="uq_dataset_memory_user_key"),
        Index("ix_dataset_memory_user_topic", "user_id", "dataset_topic"),
        Index("ix_dataset_memory_user_updated", "user_id", "updated_at"),
    )


def ensure_dataset_memory_schema() -> None:
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        DatasetMemoryRecord.__table__.create(bind=engine, checkfirst=True)
        _schema_ready = True
        logger.info("Dataset memory table ready")


def make_dataset_key(
    *,
    fingerprint: str | None = None,
    dataset_id: str | None = None,
    dataset_url: str | None = None,
    dataset_path: str | None = None,
    dataset_topic: str | None = None,
) -> str:
    """Stable key for L3 lookups (prefer fingerprint, then id/url/path/topic)."""
    if fingerprint:
        return f"fp:{fingerprint}"
    if dataset_id:
        return f"id:{dataset_id}"
    if dataset_url:
        return f"url:{hashlib.sha256(dataset_url.encode('utf-8')).hexdigest()[:32]}"
    if dataset_path:
        return f"path:{hashlib.sha256(dataset_path.encode('utf-8')).hexdigest()[:32]}"
    if dataset_topic:
        topic = dataset_topic.strip().lower()
        return f"topic:{hashlib.sha256(topic.encode('utf-8')).hexdigest()[:32]}"
    return ""


def _row_to_dataset_memory(row: DatasetMemoryRecord) -> DatasetMemory:
    return DatasetMemory(
        dataset_key=row.dataset_key,
        dataset_fingerprint=row.dataset_fingerprint,
        dataset_topic=row.dataset_topic,
        dataset_url=row.dataset_url,
        dataset_path=row.dataset_path,
        dataset_id=row.dataset_id,
        columns_frequently_used=list(row.columns_frequently_used or []),
        successful_chart_types=list(row.successful_chart_types or []),
        last_forecast_targets=list(row.last_forecast_targets or []),
        insights_digest=list(row.insights_digest or []),
        last_session_ids=list(row.last_session_ids or []),
        analysis_count=int(row.analysis_count or 0),
        last_profile_summary=dict(row.last_profile_summary or {}),
        updated_at=(
            row.updated_at.isoformat()
            if isinstance(row.updated_at, datetime)
            else str(row.updated_at or "")
        ),
    )


def load_dataset_memory(
    user_id: str,
    dataset_key: str,
) -> DatasetMemory | None:
    if not dataset_key:
        return None
    ensure_dataset_memory_schema()
    db = SessionLocal()
    try:
        row = (
            db.query(DatasetMemoryRecord)
            .filter(
                DatasetMemoryRecord.user_id == (user_id or "anonymous"),
                DatasetMemoryRecord.dataset_key == dataset_key,
            )
            .first()
        )
        if row is None:
            return None
        return _row_to_dataset_memory(row)
    finally:
        db.close()


def resolve_dataset_memory(
    user_id: str,
    *,
    fingerprint: str | None = None,
    dataset_id: str | None = None,
    dataset_url: str | None = None,
    dataset_path: str | None = None,
    dataset_topic: str | None = None,
) -> DatasetMemory | None:
    """
    Look up L3 memory trying identity keys in priority order, then
    matching URL / path / topic columns (so fp-keyed rows are found by URL).
    """
    ensure_dataset_memory_schema()
    uid = user_id or "anonymous"
    keys = []
    for kwargs in (
        {"fingerprint": fingerprint},
        {"dataset_id": dataset_id},
        {"dataset_url": dataset_url},
        {"dataset_path": dataset_path},
        {"dataset_topic": dataset_topic},
    ):
        k = make_dataset_key(**kwargs)
        if k and k not in keys:
            keys.append(k)

    for key in keys:
        hit = load_dataset_memory(uid, key)
        if hit is not None:
            return hit

    db = SessionLocal()
    try:
        q = db.query(DatasetMemoryRecord).filter(DatasetMemoryRecord.user_id == uid)
        row = None
        if fingerprint:
            row = q.filter(DatasetMemoryRecord.dataset_fingerprint == fingerprint).first()
        if row is None and dataset_url:
            row = q.filter(DatasetMemoryRecord.dataset_url == dataset_url).first()
        if row is None and dataset_path:
            row = q.filter(DatasetMemoryRecord.dataset_path == dataset_path).first()
        if row is None and dataset_id:
            row = q.filter(DatasetMemoryRecord.dataset_id == dataset_id).first()
        if row is None and dataset_topic:
            row = (
                q.filter(DatasetMemoryRecord.dataset_topic == dataset_topic)
                .order_by(DatasetMemoryRecord.updated_at.desc())
                .first()
            )
        if row is None:
            return None
        return _row_to_dataset_memory(row)
    finally:
        db.close()


def save_dataset_memory(user_id: str, memory: DatasetMemory) -> DatasetMemory:
    ensure_dataset_memory_schema()
    if not memory.dataset_key:
        return memory
    db = SessionLocal()
    try:
        row = (
            db.query(DatasetMemoryRecord)
            .filter(
                DatasetMemoryRecord.user_id == (user_id or "anonymous"),
                DatasetMemoryRecord.dataset_key == memory.dataset_key,
            )
            .first()
        )
        now = _utcnow()
        if row is None:
            row = DatasetMemoryRecord(
                id=_uuid(),
                user_id=user_id or "anonymous",
                dataset_key=memory.dataset_key,
                created_at=now,
            )
            db.add(row)

        row.dataset_fingerprint = memory.dataset_fingerprint
        row.dataset_topic = memory.dataset_topic
        row.dataset_url = memory.dataset_url
        row.dataset_path = memory.dataset_path
        row.dataset_id = memory.dataset_id
        row.columns_frequently_used = list(memory.columns_frequently_used or [])[:40]
        row.successful_chart_types = list(memory.successful_chart_types or [])[:20]
        row.last_forecast_targets = list(memory.last_forecast_targets or [])[:20]
        row.insights_digest = list(memory.insights_digest or [])[:30]
        row.last_session_ids = list(memory.last_session_ids or [])[:20]
        row.last_profile_summary = dict(memory.last_profile_summary or {})
        row.analysis_count = int(memory.analysis_count or 0)
        row.updated_at = now
        db.commit()
        memory.updated_at = now.isoformat()
        return memory
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to save dataset memory", extra={"error": str(exc)})
        return memory
    finally:
        db.close()


def load_session_memory_blob(session_id: str) -> dict[str, Any] | None:
    """Read L2 JSON from analysis_sessions.memory_state if present."""
    if not session_id:
        return None
    db = SessionLocal()
    try:
        from sqlalchemy import text

        # memory_state may not exist on older DBs
        try:
            row = db.execute(
                text(
                    """
                    SELECT memory_state FROM analysis_sessions
                    WHERE session_id = :sid
                    """
                ),
                {"sid": session_id},
            ).first()
        except Exception:
            return None
        if not row or row[0] is None:
            return None
        value = row[0]
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return None
    finally:
        db.close()


def save_session_memory_blob(session_id: str, payload: dict[str, Any]) -> None:
    """Persist L2 JSON onto analysis_sessions.memory_state."""
    if not session_id:
        return
    db = SessionLocal()
    try:
        from backend.sessions.models import AnalysisSession

        row = (
            db.query(AnalysisSession)
            .filter(AnalysisSession.session_id == session_id)
            .first()
        )
        if row is None:
            return
        # Prefer ORM attribute when present; else raw SQL
        if hasattr(row, "memory_state"):
            row.memory_state = payload  # type: ignore[attr-defined]
            db.commit()
            return
        from sqlalchemy import text

        db.execute(
            text(
                "UPDATE analysis_sessions SET memory_state = :payload "
                "WHERE session_id = :sid"
            ),
            {"sid": session_id, "payload": json.dumps(payload)},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug(
            "Session memory blob save failed",
            extra={"session_id": session_id, "error": str(exc)},
        )
    finally:
        db.close()
