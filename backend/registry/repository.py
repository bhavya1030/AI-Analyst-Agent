"""Repository layer for Dataset Registry.

Defines a storage-agnostic interface so SQLite can later be swapped for
PostgreSQL or MongoDB without changing the service API.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.core.logger import get_logger
from backend.db import SessionLocal, engine
from backend.registry.exceptions import DatasetNotFoundError
from backend.registry.models import DatasetMetadata, DatasetRegistryRecord

logger = get_logger(__name__)


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def _loads_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _loads_dict(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def record_to_metadata(record: DatasetRegistryRecord) -> DatasetMetadata:
    # Graceful read of optional columns added in registry redesign
    keywords = _loads_list(getattr(record, "keywords_json", None))
    country = _loads_list(getattr(record, "country_json", None))
    metrics = _loads_list(getattr(record, "metrics_json", None))
    domain = getattr(record, "domain", None) or "general"
    fingerprint = getattr(record, "fingerprint", None) or record.checksum
    return DatasetMetadata(
        dataset_id=record.dataset_id,
        title=record.title or "",
        topic=record.topic or "",
        description=record.description or "",
        source=record.source or "",
        source_type=record.source_type or "Other",
        download_url=record.download_url,
        local_path=record.local_path,
        file_format=record.file_format or "unknown",
        tags=_loads_list(record.tags_json),
        keywords=keywords,
        columns=_loads_list(record.columns_json),
        domain=domain or "general",
        country=country,
        metrics=metrics,
        row_count=record.row_count,
        date_range=_loads_dict(record.date_range_json),
        summary=record.summary or "",
        created_at=record.created_at or "",
        last_used=record.last_used,
        last_updated=record.last_updated or "",
        usage_count=int(record.usage_count or 0),
        checksum=record.checksum,
        fingerprint=fingerprint,
        embedding_ref=record.embedding_ref,
        is_active=bool(record.is_active if record.is_active is not None else True),
    )


def apply_metadata_to_record(record: DatasetRegistryRecord, meta: DatasetMetadata) -> None:
    record.dataset_id = meta.dataset_id
    record.title = meta.title
    record.topic = meta.topic
    record.description = meta.description or ""
    record.source = meta.source or ""
    record.source_type = meta.source_type or "Other"
    record.download_url = meta.download_url
    record.local_path = meta.local_path
    record.file_format = meta.file_format or "unknown"
    record.tags_json = _dumps(meta.tags or [])
    if hasattr(record, "keywords_json"):
        record.keywords_json = _dumps(meta.keywords or [])
    record.columns_json = _dumps(meta.columns or [])
    if hasattr(record, "domain"):
        record.domain = meta.domain or "general"
    if hasattr(record, "country_json"):
        record.country_json = _dumps(meta.country or [])
    if hasattr(record, "metrics_json"):
        record.metrics_json = _dumps(meta.metrics or [])
    record.row_count = meta.row_count
    record.date_range_json = (
        json.dumps(meta.date_range) if meta.date_range is not None else None
    )
    record.summary = meta.summary or ""
    record.created_at = meta.created_at
    record.last_used = meta.last_used
    record.last_updated = meta.last_updated
    record.usage_count = int(meta.usage_count or 0)
    record.checksum = meta.checksum
    if hasattr(record, "fingerprint"):
        record.fingerprint = meta.fingerprint or meta.checksum
    record.embedding_ref = meta.embedding_ref
    record.is_active = bool(meta.is_active)


class DatasetRegistryRepository(ABC):
    """Storage interface for dataset metadata (no retrieval policy)."""

    @abstractmethod
    def insert(self, metadata: DatasetMetadata) -> DatasetMetadata:
        ...

    @abstractmethod
    def update(self, metadata: DatasetMetadata) -> DatasetMetadata:
        ...

    @abstractmethod
    def get_by_dataset_id(self, dataset_id: str) -> Optional[DatasetMetadata]:
        ...

    @abstractmethod
    def get_by_topic(self, topic: str, *, limit: int = 20) -> list[DatasetMetadata]:
        ...

    @abstractmethod
    def list_all(self, *, limit: int = 100, active_only: bool = True) -> list[DatasetMetadata]:
        ...

    @abstractmethod
    def increment_usage(self, dataset_id: str) -> DatasetMetadata:
        ...

    @abstractmethod
    def update_last_used(self, dataset_id: str, timestamp: str) -> DatasetMetadata:
        ...

    @abstractmethod
    def delete(self, dataset_id: str) -> bool:
        ...


class SqlAlchemyDatasetRegistryRepository(DatasetRegistryRepository):
    """Default backend: SQLAlchemy (SQLite today, Postgres-compatible URL later)."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def insert(self, metadata: DatasetMetadata) -> DatasetMetadata:
        db = self._session()
        try:
            record = DatasetRegistryRecord(dataset_id=metadata.dataset_id)
            apply_metadata_to_record(record, metadata)
            db.add(record)
            db.commit()
            db.refresh(record)
            return record_to_metadata(record)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update(self, metadata: DatasetMetadata) -> DatasetMetadata:
        db = self._session()
        try:
            record = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.dataset_id == metadata.dataset_id)
                .first()
            )
            if record is None:
                raise DatasetNotFoundError(metadata.dataset_id)
            apply_metadata_to_record(record, metadata)
            db.commit()
            db.refresh(record)
            return record_to_metadata(record)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_by_dataset_id(self, dataset_id: str) -> Optional[DatasetMetadata]:
        db = self._session()
        try:
            record = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.dataset_id == dataset_id)
                .first()
            )
            return record_to_metadata(record) if record else None
        finally:
            db.close()

    def get_by_topic(self, topic: str, *, limit: int = 20) -> list[DatasetMetadata]:
        """
        Candidate recall for a topic (not final acceptance).

        Returns a broad candidate set; callers must run confidence matching
        (`backend.registry.matching`) before treating results as REGISTRY_HIT.
        """
        topic = (topic or "").strip()
        if not topic:
            return []

        db = self._session()
        try:
            normalized = topic.lower()
            tokens = [
                t
                for t in __import__("re").findall(r"[a-z0-9]+", normalized)
                if len(t) > 2
            ]
            records = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.is_active.is_(True))
                .all()
            )
            exact: list[DatasetRegistryRecord] = []
            partial: list[DatasetRegistryRecord] = []
            for record in records:
                rec_topic = (record.topic or "").lower()
                rec_title = (record.title or "").lower()
                tags = [str(t).lower() for t in _loads_list(record.tags_json)]
                keywords = [str(t).lower() for t in _loads_list(getattr(record, "keywords_json", None))]
                blob = " ".join([rec_topic, rec_title] + tags + keywords)

                if rec_topic == normalized:
                    exact.append(record)
                    continue

                # Controlled partial: shared significant token (len>=3), avoid 1–2 char noise
                shared = [t for t in tokens if len(t) >= 3 and t in blob]
                if shared:
                    partial.append(record)

            ordered = exact + partial
            return [record_to_metadata(r) for r in ordered[: max(1, limit * 3)]]
        finally:
            db.close()

    def list_all(self, *, limit: int = 100, active_only: bool = True) -> list[DatasetMetadata]:
        db = self._session()
        try:
            query = db.query(DatasetRegistryRecord)
            if active_only:
                query = query.filter(DatasetRegistryRecord.is_active.is_(True))
            records = (
                query.order_by(DatasetRegistryRecord.last_used.desc().nullslast())
                .limit(max(1, limit))
                .all()
            )
            # SQLite may not support nullslast the same way — fallback sort in Python
            if not records:
                records = query.limit(max(1, limit)).all()
            metas = [record_to_metadata(r) for r in records]
            metas.sort(
                key=lambda m: (m.last_used or "", m.usage_count or 0),
                reverse=True,
            )
            return metas[: max(1, limit)]
        finally:
            db.close()

    def increment_usage(self, dataset_id: str) -> DatasetMetadata:
        db = self._session()
        try:
            record = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.dataset_id == dataset_id)
                .first()
            )
            if record is None:
                raise DatasetNotFoundError(dataset_id)
            record.usage_count = int(record.usage_count or 0) + 1
            db.commit()
            db.refresh(record)
            return record_to_metadata(record)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_last_used(self, dataset_id: str, timestamp: str) -> DatasetMetadata:
        db = self._session()
        try:
            record = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.dataset_id == dataset_id)
                .first()
            )
            if record is None:
                raise DatasetNotFoundError(dataset_id)
            record.last_used = timestamp
            db.commit()
            db.refresh(record)
            return record_to_metadata(record)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete(self, dataset_id: str) -> bool:
        db = self._session()
        try:
            record = (
                db.query(DatasetRegistryRecord)
                .filter(DatasetRegistryRecord.dataset_id == dataset_id)
                .first()
            )
            if record is None:
                return False
            db.delete(record)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def ensure_registry_schema() -> None:
    """Create dataset_registry table if missing and migrate new columns (idempotent)."""
    DatasetRegistryRecord.__table__.create(bind=engine, checkfirst=True)
    # SQLite-friendly additive migration for registry redesign fields
    _ensure_columns(
        "dataset_registry",
        {
            "keywords_json": "TEXT DEFAULT '[]'",
            "domain": "VARCHAR DEFAULT 'general'",
            "country_json": "TEXT DEFAULT '[]'",
            "metrics_json": "TEXT DEFAULT '[]'",
            "fingerprint": "VARCHAR",
        },
    )
    logger.info("Dataset registry schema ready")


def _ensure_columns(table: str, columns: dict[str, str]) -> None:
    """ADD COLUMN IF NOT EXISTS style migration for SQLite/Postgres."""
    try:
        with engine.begin() as conn:
            existing: set[str] = set()
            try:
                # SQLAlchemy 2.x
                rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                existing = {str(r[1]).lower() for r in rows}
            except Exception:
                try:
                    rows = conn.exec_driver_sql(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = '{table}'"
                    ).fetchall()
                    existing = {str(r[0]).lower() for r in rows}
                except Exception:
                    existing = set()
            for name, ddl in columns.items():
                if name.lower() in existing:
                    continue
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"
                    )
                    logger.info(
                        "Registry schema migrated column",
                        extra={"table": table, "column": name},
                    )
                except Exception as exc:
                    logger.warning(
                        "Registry column migrate skipped",
                        extra={"column": name, "error": str(exc)},
                    )
    except Exception as exc:
        logger.warning("Registry schema migration failed", extra={"error": str(exc)})
