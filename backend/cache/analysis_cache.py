"""Durable AnalysisCache (Phase 2).

Persists expensive analysis outputs keyed by:
  kind + dataset_fingerprint (SHA256) + params_hash

Automatic invalidation: when the dataset fingerprint changes, lookups
miss and entries are recomputed. Stale rows for old fingerprints remain
harmless until optionally purged.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy import JSON

from backend.core.logger import get_logger
from backend.db import Base, SessionLocal, engine
from backend.cache.fingerprint import params_hash as hash_params
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

# Canonical kinds
KIND_EDA = "eda"
KIND_PROFILE = "profile"
KIND_EMBEDDING = "embedding"
KIND_FORECAST = "forecast"
KIND_CHART = "chart"

VALID_KINDS = frozenset(
    {KIND_EDA, KIND_PROFILE, KIND_EMBEDDING, KIND_FORECAST, KIND_CHART}
)

_schema_lock = threading.Lock()
_schema_ready = False

# Process-local L1 for hot paths (fingerprint:kind:params_hash → payload)
_L1: dict[str, Any] = {}
_L1_LOCK = threading.RLock()
_L1_MAX = 128


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class AnalysisCache(Base):
    """SQLAlchemy model for durable analysis results."""

    __tablename__ = "analysis_cache"

    id = Column(String(36), primary_key=True, default=_uuid)
    cache_key = Column(String(256), nullable=False, unique=True, index=True)
    kind = Column(String(32), nullable=False, index=True)
    dataset_fingerprint = Column(String(64), nullable=False, index=True)
    params_hash = Column(String(64), nullable=False, default="none")
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    hit_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_analysis_cache_kind_fp", "kind", "dataset_fingerprint"),
        UniqueConstraint("cache_key", name="uq_analysis_cache_key"),
    )


def ensure_analysis_cache_table() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        AnalysisCache.__table__.create(bind=engine, checkfirst=True)
        _schema_ready = True
        logger.info("AnalysisCache table ready")


def build_cache_key(kind: str, fingerprint: str, params: dict[str, Any] | None = None) -> str:
    ph = hash_params(params)
    return f"{kind}:{fingerprint}:{ph}"


def _l1_get(key: str) -> Any | None:
    with _L1_LOCK:
        if key not in _L1:
            return None
        # Move to end (simple LRU touch via re-insert)
        value = _L1.pop(key)
        _L1[key] = value
        return value


def _l1_set(key: str, value: Any) -> None:
    with _L1_LOCK:
        _L1[key] = value
        while len(_L1) > _L1_MAX:
            _L1.pop(next(iter(_L1)))


class AnalysisCacheService:
    """Get / put durable analysis results with L1 RAM + SQLite L2."""

    def __init__(self) -> None:
        ensure_analysis_cache_table()

    def get(
        self,
        kind: str,
        fingerprint: str,
        params: dict[str, Any] | None = None,
    ) -> Any | None:
        if not fingerprint or kind not in VALID_KINDS:
            return None

        key = build_cache_key(kind, fingerprint, params)
        cached = _l1_get(key)
        if cached is not None:
            logger.info(
                "Analysis cache L1 hit",
                extra={"kind": kind, "fingerprint": fingerprint[:16], "cache_key": key},
            )
            return cached

        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisCache)
                .filter(AnalysisCache.cache_key == key)
                .first()
            )
            if row is None:
                return None

            row.hit_count = int(row.hit_count or 0) + 1
            row.updated_at = _utcnow()
            payload = row.payload
            db.commit()

            _l1_set(key, payload)
            logger.info(
                "Analysis cache hit",
                extra={
                    "kind": kind,
                    "fingerprint": fingerprint[:16],
                    "hit_count": row.hit_count,
                    "cache_key": key,
                },
            )
            return payload
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Analysis cache get failed",
                extra={"kind": kind, "error": str(exc)},
            )
            return None
        finally:
            db.close()

    def put(
        self,
        kind: str,
        fingerprint: str,
        payload: Any,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        if not fingerprint or kind not in VALID_KINDS:
            return None

        key = build_cache_key(kind, fingerprint, params)
        safe_payload = sanitize_for_json(payload)
        now = _utcnow()

        _l1_set(key, safe_payload)

        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisCache)
                .filter(AnalysisCache.cache_key == key)
                .first()
            )
            if row is None:
                row = AnalysisCache(
                    id=_uuid(),
                    cache_key=key,
                    kind=kind,
                    dataset_fingerprint=fingerprint,
                    params_hash=hash_params(params),
                    payload=safe_payload,
                    created_at=now,
                    updated_at=now,
                    hit_count=0,
                )
                db.add(row)
            else:
                row.payload = safe_payload
                row.updated_at = now
                row.dataset_fingerprint = fingerprint
                row.kind = kind
                row.params_hash = hash_params(params)

            db.commit()
            logger.info(
                "Analysis cache store",
                extra={
                    "kind": kind,
                    "fingerprint": fingerprint[:16],
                    "cache_key": key,
                },
            )
            return key
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Analysis cache put failed",
                extra={"kind": kind, "error": str(exc)},
            )
            return None
        finally:
            db.close()

    def get_or_compute(
        self,
        kind: str,
        fingerprint: str,
        compute_fn: Callable[[], Any],
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, bool]:
        """
        Return (payload, from_cache).

        On miss, calls compute_fn(), stores result, returns (result, False).
        """
        hit = self.get(kind, fingerprint, params)
        if hit is not None:
            return hit, True

        result = compute_fn()
        if result is not None:
            self.put(kind, fingerprint, result, params)
        return result, False

    def invalidate_fingerprint(self, fingerprint: str) -> int:
        """Explicit purge for a fingerprint (optional; not required for correctness)."""
        if not fingerprint:
            return 0
        with _L1_LOCK:
            drop = [k for k in _L1 if f":{fingerprint}:" in k]
            for k in drop:
                _L1.pop(k, None)

        db = SessionLocal()
        try:
            deleted = (
                db.query(AnalysisCache)
                .filter(AnalysisCache.dataset_fingerprint == fingerprint)
                .delete(synchronize_session=False)
            )
            db.commit()
            return int(deleted or 0)
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Analysis cache invalidate failed",
                extra={"error": str(exc)},
            )
            return 0
        finally:
            db.close()


_service: AnalysisCacheService | None = None
_service_lock = threading.Lock()


def get_analysis_cache() -> AnalysisCacheService:
    global _service
    with _service_lock:
        if _service is None:
            _service = AnalysisCacheService()
        return _service
