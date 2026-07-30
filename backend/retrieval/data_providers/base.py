"""Production data-provider interface for open-dataset discovery (Retrieval v2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence


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
    # Retrieval v2 fields
    confidence: float = 0.5
    country: list[str] = field(default_factory=list)
    metric: Optional[str] = None
    time_period: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """Provenance-rich metadata for registry / learning / acquisition."""
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
            "confidence": float(self.confidence),
            "country": list(self.country or []),
            "metric": self.metric,
            "time_period": self.time_period,
            "download_timestamp": _utc_now_iso(),
            "download_date": _utc_now_iso()[:10],
            **{k: v for k, v in (self.extra or {}).items() if k not in {"source_type"}},
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
            "candidates": [c.to_dict() for c in self.candidates],
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class DataProvider(ABC):
    """One external data source capable of resolving topics to downloadable files."""

    name: str = "base"
    # Higher = preferred earlier for matching topics
    priority: int = 50
    # Domains this provider is strong at (macro, climate, sports, finance, ...)
    domains: Sequence[str] = ()

    @abstractmethod
    def supports(self, topic: str, keywords: list[str]) -> bool:
        """Cheap affinity check — whether this provider should be tried."""

    @abstractmethod
    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        """Return ranked candidates with direct download URLs (never HTML search pages)."""

    def preferred_for(self, topic: str, keywords: list[str]) -> int:
        """Affinity score used for ordering providers (higher first)."""
        return self.priority if self.supports(topic, keywords) else -1

    def score_for_context(
        self,
        topic: str,
        keywords: list[str],
        *,
        country: Sequence[str] | None = None,
        metric: str | None = None,
        time_period: str | None = None,
        domain: str | None = None,
        aliases: Sequence[str] | None = None,
    ) -> int:
        """
        Retrieval v2 selection: topic + country + metric + time period.

        Returns affinity score (higher = try earlier). Negative = skip unless fallback.
        """
        base = self.preferred_for(topic, keywords)
        score = base if base >= 0 else 0
        blob = f"{topic} {' '.join(keywords)} {metric or ''} {' '.join(country or [])}".lower()

        if domain and self.domains and domain in self.domains:
            score += 40
        if metric and metric.lower() in blob:
            score += 15
        if country and any(c.lower() in blob for c in country):
            score += 10
        if time_period:
            score += 5
        if aliases and any(a in (self.domains or ()) for a in aliases):
            score += 20
        if base < 0 and score < 20:
            return -1
        return score if score > 0 else base
