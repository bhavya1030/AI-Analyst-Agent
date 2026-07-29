"""Dataset Registry models: rich metadata + SQLAlchemy persistence entity.

Metadata only — no DataFrames, charts, insights, or session payloads.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, Column, Integer, String, Text

from backend.db import Base


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_dataset_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Domain model (storage-backend agnostic)
# ---------------------------------------------------------------------------


@dataclass
class DatasetMetadata:
    """Canonical registry record. Safe to serialize; never holds analysis artifacts."""

    dataset_id: str
    title: str  # Dataset Name
    topic: str
    description: str = ""
    source: str = ""
    source_type: str = "Other"  # API | Web | GitHub | HuggingFace | data.gov | Upload | UserURL | Other
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    file_format: str = "unknown"  # csv | json | parquet | xlsx | xls | unknown
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    domain: str = "general"
    country: list[str] = field(default_factory=list)  # countries / regions covered
    metrics: list[str] = field(default_factory=list)  # measurable fields / KPIs
    row_count: Optional[int] = None
    date_range: Optional[dict[str, Any]] = None  # e.g. {"start": "2019", "end": "2024"}
    summary: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    last_used: Optional[str] = None
    last_updated: str = field(default_factory=_utc_now_iso)
    usage_count: int = 0
    checksum: Optional[str] = None
    fingerprint: Optional[str] = None  # content / schema fingerprint (often == checksum)
    embedding_ref: Optional[str] = None  # semantic index reference
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetMetadata":
        if not data:
            raise ValueError("Empty metadata dict")

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}

        # Aliases from older payloads / learning
        if "country" not in payload and data.get("countries_regions"):
            payload["country"] = data.get("countries_regions")
        if "keywords" not in payload and data.get("topic_keywords"):
            payload["keywords"] = data.get("topic_keywords")
        if not payload.get("fingerprint") and data.get("checksum"):
            payload["fingerprint"] = data.get("checksum")
        if not payload.get("domain") and data.get("domain"):
            payload["domain"] = data.get("domain")

        if not payload.get("dataset_id"):
            payload["dataset_id"] = new_dataset_id()
        if not payload.get("created_at"):
            payload["created_at"] = _utc_now_iso()
        if not payload.get("last_updated"):
            payload["last_updated"] = payload["created_at"]

        payload.setdefault("title", "")
        payload.setdefault("topic", "")
        if payload.get("title") is None:
            payload["title"] = ""
        if payload.get("topic") is None:
            payload["topic"] = ""

        for key in ("tags", "columns", "keywords", "country", "metrics"):
            value = payload.get(key)
            if value is None:
                payload[key] = []
            elif not isinstance(value, list):
                payload[key] = [str(value)]

        if payload.get("usage_count") is None:
            payload["usage_count"] = 0
        if not payload.get("domain"):
            payload["domain"] = "general"
        if not payload.get("fingerprint") and payload.get("checksum"):
            payload["fingerprint"] = payload.get("checksum")

        return cls(**payload)

    def touch_updated(self) -> None:
        self.last_updated = _utc_now_iso()


# ---------------------------------------------------------------------------
# SQLAlchemy entity (default backend: SQLite via project DATABASE_URL)
# ---------------------------------------------------------------------------


class DatasetRegistryRecord(Base):
    """ORM row for dataset_registry table. Mirrors DatasetMetadata fields only."""

    __tablename__ = "dataset_registry"

    dataset_id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="")
    topic = Column(String, nullable=False, index=True, default="")
    description = Column(Text, default="")
    source = Column(String, default="")
    source_type = Column(String, default="Other")
    download_url = Column(String, nullable=True, index=True)
    local_path = Column(String, nullable=True)
    file_format = Column(String, default="unknown")
    tags_json = Column(Text, default="[]")
    keywords_json = Column(Text, default="[]")
    columns_json = Column(Text, default="[]")
    domain = Column(String, default="general", index=True)
    country_json = Column(Text, default="[]")
    metrics_json = Column(Text, default="[]")
    row_count = Column(Integer, nullable=True)
    date_range_json = Column(Text, nullable=True)
    summary = Column(Text, default="")
    created_at = Column(String, nullable=False)
    last_used = Column(String, nullable=True)
    last_updated = Column(String, nullable=False)
    usage_count = Column(Integer, default=0)
    checksum = Column(String, nullable=True, index=True)
    fingerprint = Column(String, nullable=True, index=True)
    embedding_ref = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
