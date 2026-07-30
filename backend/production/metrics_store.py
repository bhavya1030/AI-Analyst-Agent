"""SQLite-backed metrics store for performance monitoring.

Persists per-request samples so /performance and /metrics can report
P50 / P95 / avg / min / max across process restarts (when DB is shared).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal = None
_lock = threading.RLock()
_ready = False


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MetricSample(Base):
    """One request / pipeline run sample."""

    __tablename__ = "metric_samples"

    id = Column(String(36), primary_key=True)
    created_at = Column(String(40), nullable=False, index=True)
    created_ts = Column(Float, nullable=False, index=True)
    route = Column(String(256), nullable=True, index=True)
    method = Column(String(16), nullable=True)
    status_code = Column(Integer, nullable=True)
    session_id = Column(String(128), nullable=True, index=True)
    success = Column(Integer, nullable=False, default=1)  # 1/0
    cache_hit = Column(Integer, nullable=False, default=0)
    total_ms = Column(Float, nullable=False, default=0.0)
    memory_mb = Column(Float, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    forecast_model = Column(String(128), nullable=True)
    chart_type = Column(String(64), nullable=True)
    provider = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)
    # JSON blob: stage latencies, provider latencies, extras
    stages_json = Column(Text, nullable=True)
    labels_json = Column(Text, nullable=True)


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = settings.DATABASE_URL
        connect_args = {}
        if str(url).startswith("sqlite"):
            connect_args = {"check_same_thread": False, "timeout": 30.0}
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def ensure_metrics_schema() -> None:
    global _ready
    with _lock:
        if _ready:
            return
        eng = _get_engine()
        Base.metadata.create_all(eng, tables=[MetricSample.__table__])
        _ready = True
        logger.info("Metrics store schema ready")


def record_metric_sample(
    *,
    route: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    session_id: str | None = None,
    success: bool = True,
    cache_hit: bool = False,
    total_ms: float = 0.0,
    memory_mb: float | None = None,
    cpu_percent: float | None = None,
    forecast_model: str | None = None,
    chart_type: str | None = None,
    provider: str | None = None,
    error: str | None = None,
    stages: dict[str, Any] | None = None,
    labels: dict[str, Any] | None = None,
) -> str:
    """Insert one metrics sample. Returns sample id. Never raises to callers."""
    try:
        ensure_metrics_schema()
        sample_id = str(uuid.uuid4())
        now = time.time()
        row = MetricSample(
            id=sample_id,
            created_at=_utc_iso(),
            created_ts=now,
            route=(route or "")[:256] or None,
            method=(method or "")[:16] or None,
            status_code=status_code,
            session_id=(session_id or "")[:128] or None,
            success=1 if success else 0,
            cache_hit=1 if cache_hit else 0,
            total_ms=float(total_ms or 0.0),
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            forecast_model=(forecast_model or "")[:128] or None,
            chart_type=(chart_type or "")[:64] or None,
            provider=(provider or "")[:128] or None,
            error=(error or "")[:2000] or None,
            stages_json=json.dumps(stages or {}, default=str),
            labels_json=json.dumps(labels or {}, default=str),
        )
        db: Session = _SessionLocal()  # type: ignore[misc]
        try:
            db.add(row)
            db.commit()
        finally:
            db.close()
        return sample_id
    except Exception as exc:
        logger.debug("metric sample persist failed", extra={"error": str(exc)})
        return ""


def list_metric_samples(
    *,
    limit: int = 500,
    since_ts: float | None = None,
    route: str | None = None,
) -> list[dict[str, Any]]:
    ensure_metrics_schema()
    limit = max(1, min(int(limit or 500), 5000))
    db: Session = _SessionLocal()  # type: ignore[misc]
    try:
        q = db.query(MetricSample)
        if since_ts is not None:
            q = q.filter(MetricSample.created_ts >= float(since_ts))
        if route:
            q = q.filter(MetricSample.route == route)
        rows = q.order_by(MetricSample.created_ts.desc()).limit(limit).all()
        out: list[dict[str, Any]] = []
        for r in rows:
            stages = {}
            labels = {}
            try:
                stages = json.loads(r.stages_json or "{}")
            except Exception:
                stages = {}
            try:
                labels = json.loads(r.labels_json or "{}")
            except Exception:
                labels = {}
            out.append(
                {
                    "id": r.id,
                    "created_at": r.created_at,
                    "created_ts": r.created_ts,
                    "route": r.route,
                    "method": r.method,
                    "status_code": r.status_code,
                    "session_id": r.session_id,
                    "success": bool(r.success),
                    "cache_hit": bool(r.cache_hit),
                    "total_ms": r.total_ms,
                    "memory_mb": r.memory_mb,
                    "cpu_percent": r.cpu_percent,
                    "forecast_model": r.forecast_model,
                    "chart_type": r.chart_type,
                    "provider": r.provider,
                    "error": r.error,
                    "stages": stages,
                    "labels": labels,
                }
            )
        return out
    finally:
        db.close()


def clear_metric_samples() -> int:
    """Delete all samples (tests)."""
    ensure_metrics_schema()
    db: Session = _SessionLocal()  # type: ignore[misc]
    try:
        n = db.query(MetricSample).delete()
        db.commit()
        return int(n or 0)
    finally:
        db.close()


def metrics_store_stats() -> dict[str, Any]:
    ensure_metrics_schema()
    db: Session = _SessionLocal()  # type: ignore[misc]
    try:
        n = db.query(MetricSample).count()
        return {"samples": int(n), "table": "metric_samples"}
    finally:
        db.close()
