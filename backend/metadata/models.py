"""Generated dataset metadata models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Labels that must never be shown as the dataset name in the UI.
PLACEHOLDER_TOPICS = frozenset(
    {
        "user provided dataset",
        "user provided url",
        "general dataset",
        "active session dataset",
        "dataset",
        "untitled dataset",
        "untitled",
        "unknown",
        "unknown topic",
        "",
    }
)


def is_placeholder_label(value: str | None) -> bool:
    return (value or "").strip().lower() in PLACEHOLDER_TOPICS


@dataclass
class GeneratedDatasetMetadata:
    """Human-facing + registry-ready metadata inferred from a dataset."""

    title: str
    description: str = ""
    domain: str = "general"
    country: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    time_column: Optional[str] = None
    primary_entity: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    summary: str = ""
    topic: str = ""
    columns: list[str] = field(default_factory=list)
    row_count: Optional[int] = None
    date_range: Optional[dict[str, Any]] = None
    dataset_type: str = "unknown"
    file_format: str = "unknown"
    local_path: Optional[str] = None
    download_url: Optional[str] = None
    source: str = ""
    source_type: str = "Other"
    dataset_id: Optional[str] = None
    checksum: Optional[str] = None
    generated_at: str = field(default_factory=_utc_now_iso)
    generator: str = "rule_based"  # rule_based | rule_based+llm
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_registry_dict(self) -> dict[str, Any]:
        """Payload suitable for DatasetMetadata.from_dict / insert_dataset."""
        return {
            "dataset_id": self.dataset_id,
            "title": self.title,
            "topic": self.topic or self.title,
            "description": self.description,
            "source": self.source,
            "source_type": self.source_type,
            "download_url": self.download_url,
            "local_path": self.local_path,
            "file_format": self.file_format,
            "tags": list(self.tags),
            "keywords": list(self.keywords),
            "columns": list(self.columns),
            "domain": self.domain or "general",
            "country": list(self.country),
            "metrics": list(self.metrics),
            "row_count": self.row_count,
            "date_range": self.date_range,
            "summary": self.summary,
            "checksum": self.checksum,
            "fingerprint": self.checksum,
            "is_active": True,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneratedDatasetMetadata":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in (data or {}).items() if k in known}
        payload.setdefault("title", "Untitled dataset")
        for key in ("country", "metrics", "tags", "keywords", "columns", "notes"):
            if payload.get(key) is None:
                payload[key] = []
            elif not isinstance(payload[key], list):
                payload[key] = [str(payload[key])]
        return cls(**payload)
