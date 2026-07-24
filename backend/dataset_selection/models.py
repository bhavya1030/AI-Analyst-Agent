"""Models for Dataset Selection (pick best candidate among many)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class DatasetCandidate:
    """One candidate dataset offered to the selector (metadata only)."""

    candidate_id: str
    title: str = ""
    topic: str = ""
    description: str = ""
    source: str = ""
    source_type: str = ""
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    summary: str = ""
    similarity_score: Optional[float] = None  # semantic score if present
    rank_hint: Optional[float] = None
    provider: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, index: int = 0) -> "DatasetCandidate":
        if not isinstance(data, dict):
            data = {}
        cid = (
            data.get("candidate_id")
            or data.get("dataset_id")
            or data.get("registry_id")
            or data.get("id")
            or f"candidate-{index}"
        )
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        columns = data.get("columns") or data.get("column_names") or []
        if not isinstance(columns, list):
            columns = [str(columns)]
        return cls(
            candidate_id=str(cid),
            title=str(data.get("title") or data.get("name") or ""),
            topic=str(data.get("topic") or ""),
            description=str(data.get("description") or "")[:500],
            source=str(data.get("source") or ""),
            source_type=str(data.get("source_type") or ""),
            download_url=data.get("download_url") or data.get("url"),
            local_path=data.get("local_path"),
            tags=[str(t) for t in tags],
            columns=[str(c) for c in columns],
            summary=str(data.get("summary") or "")[:500],
            similarity_score=_as_float(data.get("similarity_score")),
            rank_hint=_as_float(data.get("rank_hint")),
            provider=str(data.get("provider") or data.get("provider_name") or ""),
            extra={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "candidate_id",
                    "dataset_id",
                    "registry_id",
                    "id",
                    "title",
                    "name",
                    "topic",
                    "description",
                    "source",
                    "source_type",
                    "download_url",
                    "url",
                    "local_path",
                    "tags",
                    "columns",
                    "column_names",
                    "summary",
                    "similarity_score",
                    "rank_hint",
                    "provider",
                    "provider_name",
                }
            },
        )


@dataclass
class SelectionInput:
    """Selector input: user question + candidate list."""

    question: str
    candidates: list[DatasetCandidate] = field(default_factory=list)
    topic: str = ""

    @classmethod
    def from_raw(
        cls,
        question: str,
        candidates: list[Any],
        *,
        topic: str = "",
    ) -> "SelectionInput":
        parsed: list[DatasetCandidate] = []
        for i, c in enumerate(candidates or []):
            if isinstance(c, DatasetCandidate):
                parsed.append(c)
            elif isinstance(c, dict):
                parsed.append(DatasetCandidate.from_dict(c, index=i))
            elif hasattr(c, "to_dict"):
                parsed.append(DatasetCandidate.from_dict(c.to_dict(), index=i))
            else:
                parsed.append(
                    DatasetCandidate(
                        candidate_id=f"candidate-{i}",
                        title=str(c),
                    )
                )
        return cls(question=(question or "").strip(), candidates=parsed, topic=(topic or "").strip())


@dataclass
class SelectionResult:
    """Selector output: best dataset + reasoning."""

    best_dataset: Optional[DatasetCandidate]
    reason: str
    confidence: float  # 0.0 – 1.0
    selector: str = "rule_based"
    scores: dict[str, float] = field(default_factory=dict)  # candidate_id → score
    alternatives: list[DatasetCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_dataset": self.best_dataset.to_dict() if self.best_dataset else None,
            "reason": self.reason,
            "confidence": self.confidence,
            "selector": self.selector,
            "scores": self.scores,
            "alternatives": [a.to_dict() for a in self.alternatives],
        }


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
