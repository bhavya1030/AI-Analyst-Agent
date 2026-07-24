"""Dataset intelligence profile — structure only, no EDA stats or charts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class DatasetProfile:
    """Structural intelligence profile for a dataset file."""

    dataset_type: str  # time_series | tabular | geospatial | text | unknown
    row_count: int = 0
    column_names: list[str] = field(default_factory=list)
    column_types: dict[str, str] = field(default_factory=dict)
    time_column: Optional[str] = None
    entity_column: Optional[str] = None
    numeric_metrics: list[str] = field(default_factory=list)
    categorical_fields: list[str] = field(default_factory=list)
    date_range: Optional[dict[str, Any]] = None  # {"start": ..., "end": ...}
    countries_regions: list[str] = field(default_factory=list)
    topic_keywords: list[str] = field(default_factory=list)
    domain: str = "general"
    local_path: str = ""
    file_format: str = "unknown"
    profiled_at: str = field(default_factory=_utc_now_iso)
    profiler: str = "rule_based"  # rule_based | llm (future)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetProfile":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in (data or {}).items() if k in known}
        payload.setdefault("dataset_type", "unknown")
        payload.setdefault("row_count", 0)
        payload.setdefault("column_names", [])
        payload.setdefault("column_types", {})
        payload.setdefault("numeric_metrics", [])
        payload.setdefault("categorical_fields", [])
        payload.setdefault("countries_regions", [])
        payload.setdefault("topic_keywords", [])
        payload.setdefault("domain", "general")
        payload.setdefault("local_path", "")
        payload.setdefault("file_format", "unknown")
        payload.setdefault("profiled_at", _utc_now_iso())
        payload.setdefault("profiler", "rule_based")
        payload.setdefault("notes", [])
        return cls(**payload)
