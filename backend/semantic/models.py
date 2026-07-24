"""Models for semantic dataset search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SemanticDocument:
    """Text document indexed for a registry dataset."""

    registry_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    indexed_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticSearchResult:
    """One hit from semantic search."""

    registry_id: str
    similarity_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_index_text(
    *,
    title: str = "",
    description: str = "",
    tags: list[str] | None = None,
    topic_keywords: list[str] | None = None,
    summary: str = "",
    topic: str = "",
) -> str:
    """Concatenate fields used for embedding (title, description, tags, keywords, summary)."""
    parts: list[str] = []
    for value in (title, topic, description, summary):
        v = (value or "").strip()
        if v:
            parts.append(v)
    for group in (tags or [], topic_keywords or []):
        for item in group:
            s = str(item).strip()
            if s and s not in parts:
                parts.append(s)
    return " | ".join(parts)
