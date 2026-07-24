"""Abstract open-data source connector used by Official API / Internet providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SourceCandidate:
    """A discovered dataset resource (metadata + location only)."""

    title: str
    topic: str
    download_url: Optional[str] = None
    source: str = ""
    source_type: str = "Other"
    description: str = ""
    file_format: str = "unknown"
    tags: list[str] = field(default_factory=list)
    rank_hint: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("rank_hint", None)
        payload.pop("extra", None)
        payload.update(self.extra or {})
        return payload


class DataSource(ABC):
    """One external catalog/API. Retrieval providers call these; they never load DataFrames."""

    name: str = "source"
    source_type: str = "Other"

    @abstractmethod
    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        ...
