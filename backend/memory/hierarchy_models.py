"""Memory hierarchy domain models (Phase 5).

Level 1 — Conversation Memory: recent messages (verbatim window)
Level 2 — Session Memory: current analysis working set
Level 3 — Dataset Memory: prior work on the same dataset
Level 4 — Knowledge Memory: registry + learned datasets

No DataFrames are stored at any level.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ConversationMessage:
    role: str
    content: str
    seq: Optional[int] = None
    message_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConversationMessage":
        data = data or {}
        return cls(
            role=str(data.get("role") or "user"),
            content=str(data.get("content") or ""),
            seq=data.get("seq"),
            message_id=data.get("message_id") or data.get("id"),
        )


@dataclass
class ConversationMemory:
    """Level 1 — sliding window of recent chat turns + turn anchors."""

    messages: list[ConversationMessage] = field(default_factory=list)
    window_size: int = 12
    conversation_summary: str = ""
    # Memory v2 anchors for continuity
    current_intent: Optional[str] = None
    previous_question: Optional[str] = None
    current_response: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": 1,
            "name": "conversation",
            "messages": [m.to_dict() for m in self.messages],
            "window_size": self.window_size,
            "conversation_summary": self.conversation_summary,
            "current_intent": self.current_intent,
            "previous_question": self.previous_question,
            "current_response": self.current_response,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConversationMemory":
        data = data or {}
        return cls(
            messages=[
                ConversationMessage.from_dict(m) for m in (data.get("messages") or [])
            ],
            window_size=int(data.get("window_size") or 12),
            conversation_summary=str(data.get("conversation_summary") or ""),
            current_intent=data.get("current_intent"),
            previous_question=data.get("previous_question"),
            current_response=data.get("current_response"),
        )


@dataclass
class SessionMemory:
    """Level 2 — active analysis context for this session (no live DataFrame)."""

    session_id: str = ""
    last_intent: Optional[str] = None
    last_operation: Optional[str] = None
    last_chart_type: Optional[str] = None
    last_forecast_target: Optional[str] = None
    last_columns: list[str] = field(default_factory=list)
    last_column: Optional[str] = None
    selected_columns: list[str] = field(default_factory=list)
    dataset_topic: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_path: Optional[str] = None
    dataset_url: Optional[str] = None
    dataset_fingerprint: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_profile_summary: dict[str, Any] = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    # Artifact / forecast continuity (JSON-safe refs only)
    chart_types: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    forecast_model: Optional[str] = None
    forecast_horizon: Optional[int] = None
    has_forecast: bool = False
    last_insight: Optional[str] = None
    last_query: Optional[str] = None
    hypotheses: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    detected_patterns: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": 2,
            "name": "session",
            **{k: v for k, v in asdict(self).items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SessionMemory":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        for key in (
            "last_columns",
            "selected_columns",
            "metrics",
            "entities",
            "filters",
            "hypotheses",
            "recommended_next_steps",
            "detected_patterns",
            "chart_types",
            "artifact_ids",
        ):
            payload.setdefault(key, [])
        payload.setdefault("dataset_profile_summary", {})
        payload.setdefault("has_forecast", False)
        return cls(**payload)


@dataclass
class DatasetMemory:
    """Level 3 — cumulative knowledge about one dataset across sessions."""

    dataset_key: str = ""
    dataset_fingerprint: Optional[str] = None
    dataset_topic: Optional[str] = None
    dataset_url: Optional[str] = None
    dataset_path: Optional[str] = None
    dataset_id: Optional[str] = None
    columns_frequently_used: list[str] = field(default_factory=list)
    successful_chart_types: list[str] = field(default_factory=list)
    last_forecast_targets: list[str] = field(default_factory=list)
    insights_digest: list[str] = field(default_factory=list)
    last_session_ids: list[str] = field(default_factory=list)
    analysis_count: int = 0
    last_profile_summary: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": 3,
            "name": "dataset",
            **{k: v for k, v in asdict(self).items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DatasetMemory":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        for key in (
            "columns_frequently_used",
            "successful_chart_types",
            "last_forecast_targets",
            "insights_digest",
            "last_session_ids",
        ):
            payload.setdefault(key, [])
        payload.setdefault("last_profile_summary", {})
        payload.setdefault("analysis_count", 0)
        return cls(**payload)


@dataclass
class KnowledgeMemory:
    """Level 4 — product knowledge: learned datasets + registry."""

    learned_datasets: list[dict[str, Any]] = field(default_factory=list)
    registry_datasets: list[dict[str, Any]] = field(default_factory=list)
    topic_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": 4,
            "name": "knowledge",
            "learned_datasets": list(self.learned_datasets),
            "registry_datasets": list(self.registry_datasets),
            "topic_hint": self.topic_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "KnowledgeMemory":
        data = data or {}
        return cls(
            learned_datasets=list(data.get("learned_datasets") or []),
            registry_datasets=list(data.get("registry_datasets") or []),
            topic_hint=str(data.get("topic_hint") or ""),
        )


@dataclass
class MemoryBundle:
    """Full hierarchy snapshot for one request."""

    session_id: str
    user_id: str = "anonymous"
    l1_conversation: ConversationMemory = field(default_factory=ConversationMemory)
    l2_session: SessionMemory = field(default_factory=SessionMemory)
    l3_dataset: OptionalMemory = field(default_factory=DatasetMemory)
    l4_knowledge: KnowledgeMemory = field(default_factory=KnowledgeMemory)
    loaded_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "loaded_at": self.loaded_at,
            "l1_conversation": self.l1_conversation.to_dict(),
            "l2_session": self.l2_session.to_dict(),
            "l3_dataset": self.l3_dataset.to_dict(),
            "l4_knowledge": self.l4_knowledge.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MemoryBundle":
        data = data or {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            user_id=str(data.get("user_id") or "anonymous"),
            l1_conversation=ConversationMemory.from_dict(data.get("l1_conversation")),
            l2_session=SessionMemory.from_dict(data.get("l2_session")),
            l3_dataset=DatasetMemory.from_dict(data.get("l3_dataset")),
            l4_knowledge=KnowledgeMemory.from_dict(data.get("l4_knowledge")),
            loaded_at=str(data.get("loaded_at") or _utc_now_iso()),
        )
