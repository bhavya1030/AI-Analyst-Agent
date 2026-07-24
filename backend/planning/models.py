"""Models for multi-dataset planning (planning only — no execution)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from backend.retrieval.models import DatasetRequest


class MultiDatasetIntent(str, Enum):
    SINGLE = "single"
    COMPARISON = "comparison"
    CORRELATION = "correlation"
    FORECASTING = "forecasting"
    MULTI_METRIC = "multi_metric"


@dataclass
class MultiDatasetPlan:
    """Planner output for one or more dataset retrieval requests."""

    requests: list[DatasetRequest] = field(default_factory=list)
    intent: MultiDatasetIntent = MultiDatasetIntent.SINGLE
    metrics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # countries / regions if detected
    question: str = ""
    is_multi: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": [
                {
                    "topic": r.topic,
                    "question": r.question,
                    "force_new_topic": r.force_new_topic,
                    "session_id": r.session_id,
                }
                for r in self.requests
            ],
            "intent": self.intent.value if isinstance(self.intent, MultiDatasetIntent) else self.intent,
            "metrics": self.metrics,
            "entities": self.entities,
            "question": self.question,
            "is_multi": self.is_multi,
            "notes": self.notes,
        }

    def topics(self) -> list[str]:
        return [r.topic for r in self.requests if r.topic]
