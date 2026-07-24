"""Sidecar file metadata for the Dataset Library.

Intentionally minimal — not a Dataset Registry record.
No analysis, charts, columns schema beyond format, or session fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class LibraryFileMetadata:
    """metadata.json stored next to the data file."""

    dataset_id: str
    checksum: str
    download_time: str
    source: str = ""
    file_format: str = "csv"
    version: str = "1"
    # Library-only location hints (not registry schema)
    relative_dir: str = ""
    data_filename: str = "dataset.csv"
    topic: str = ""  # used only for path rebuild; not registry duplication of full meta

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LibraryFileMetadata":
        if not data or not data.get("dataset_id"):
            raise ValueError("dataset_id required in library metadata")
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload.setdefault("checksum", "")
        payload.setdefault("download_time", _utc_now_iso())
        payload.setdefault("source", "")
        payload.setdefault("file_format", "csv")
        payload.setdefault("version", "1")
        payload.setdefault("relative_dir", "")
        payload.setdefault("data_filename", "dataset.csv")
        payload.setdefault("topic", "")
        return cls(**payload)


@dataclass
class SaveResult:
    """Return value of save/replace operations."""

    dataset_id: str
    local_path: str
    checksum: str
    file_format: str
    relative_dir: str
    metadata_path: str
    version: str = "1"
    replaced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
