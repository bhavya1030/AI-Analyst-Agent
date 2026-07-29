"""Production data-provider interface for open-dataset discovery."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class DatasetCandidate:
    """A provider-discovered downloadable dataset candidate."""

    title: str
    topic: str
    download_url: str
    provider: str
    source_url: Optional[str] = None
    license: Optional[str] = None
    dataset_version: Optional[str] = None
    file_format: str = "unknown"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    rank: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "topic": self.topic,
            "download_url": self.download_url,
            "source_url": self.source_url or self.download_url,
            "provider": self.provider,
            "source": self.provider,
            "source_type": self.extra.get("source_type") or self.provider,
            "license": self.license,
            "dataset_version": self.dataset_version,
            "file_format": self.file_format,
            "description": self.description,
            "tags": list(self.tags or []),
            "download_timestamp": _utc_now_iso(),
            **{k: v for k, v in (self.extra or {}).items() if k not in {"source_type"}},
        }


@dataclass
class ProviderSearchResult:
    """Outcome of a single provider search attempt."""

    provider: str
    candidates: list[DatasetCandidate] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "candidates": [asdict(c) for c in self.candidates],
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class DataProvider(ABC):
    """One external data source capable of resolving topics to downloadable files."""

    name: str = "base"
    # Higher = preferred earlier for matching topics
    priority: int = 50

    @abstractmethod
    def supports(self, topic: str, keywords: list[str]) -> bool:
        """Cheap affinity check — whether this provider should be tried."""

    @abstractmethod
    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        """Return ranked candidates with direct download URLs (never HTML search pages)."""

    def preferred_for(self, topic: str, keywords: list[str]) -> int:
        """Affinity score used for ordering providers (higher first)."""
        return self.priority if self.supports(topic, keywords) else -1
