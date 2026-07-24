"""Acquisition request/result models — no DataFrames or analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class AcquisitionResult:
    success: bool
    local_path: Optional[str] = None
    checksum: Optional[str] = None
    detected_format: Optional[str] = None
    dataset_size: Optional[int] = None
    acquisition_time: str = field(default_factory=_utc_now_iso)
    errors: list[str] = field(default_factory=list)
    dataset_id: Optional[str] = None
    source_url: Optional[str] = None
    provider: Optional[str] = None
    reused_existing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def failure(cls, *errors: str, **kwargs) -> "AcquisitionResult":
        kwargs.setdefault("acquisition_time", _utc_now_iso())
        kwargs["success"] = False
        kwargs["errors"] = [str(e) for e in errors if e]
        return cls(**kwargs)
