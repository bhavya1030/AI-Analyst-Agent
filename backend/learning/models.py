"""Learning service models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LearningAction(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass
class LearningResult:
    action_taken: LearningAction
    registry_id: Optional[str] = None
    created: bool = False
    updated: bool = False
    duplicate_detected: bool = False
    reason: str = ""
    embedding_ref: Optional[str] = None  # future plug-in output
    learned_at: str = field(default_factory=_utc_now_iso)
    metadata_snapshot: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action_taken"] = (
            self.action_taken.value
            if isinstance(self.action_taken, LearningAction)
            else self.action_taken
        )
        return payload


@dataclass
class LearningInput:
    """Normalized inputs for learn_dataset (from heterogeneous result types)."""

    dataset_id: Optional[str] = None
    title: str = ""
    topic: str = ""
    description: str = ""
    source: str = ""
    source_type: str = "Other"
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    file_format: str = "unknown"
    tags: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: Optional[int] = None
    date_range: Optional[dict[str, Any]] = None
    summary: str = ""
    checksum: Optional[str] = None
    embedding_ref: Optional[str] = None
    # Profile extras stored in summary/tags (registry schema has no dedicated columns)
    domain: str = "general"
    time_column: Optional[str] = None
    entity_column: Optional[str] = None
    countries_regions: list[str] = field(default_factory=list)
    topic_keywords: list[str] = field(default_factory=list)
    dataset_type: str = "unknown"
