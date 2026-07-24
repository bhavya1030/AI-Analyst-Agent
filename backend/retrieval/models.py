"""Request / response models for Dataset Retrieval Agent.

No DataFrames. Location + metadata pointers only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class RetrievalStatus(str, Enum):
    SESSION_HIT = "SESSION_HIT"
    REGISTRY_HIT = "REGISTRY_HIT"
    STALE_REGISTRY_ENTRY = "STALE_REGISTRY_ENTRY"
    SEMANTIC_HIT = "SEMANTIC_HIT"
    API_HIT = "API_HIT"
    INTERNET_HIT = "INTERNET_HIT"
    SEARCH_REQUIRED = "SEARCH_REQUIRED"
    NOT_FOUND = "NOT_FOUND"


class NextAction(str, Enum):
    """What the caller (Planner / future graph) should do next."""

    USE_SESSION = "USE_SESSION"
    USE_LOCAL_FILE = "USE_LOCAL_FILE"
    USE_DOWNLOAD_URL = "USE_DOWNLOAD_URL"
    RUN_INTERNET_SEARCH = "RUN_INTERNET_SEARCH"
    ASK_USER_UPLOAD = "ASK_USER_UPLOAD"
    NONE = "NONE"


@dataclass
class DatasetRequest:
    """Input accepted by the Retrieval Agent."""

    topic: str
    session_id: Optional[str] = None
    # Optional in-process session snapshot (preferred when LangGraph state is available)
    session_topic: Optional[str] = None
    session_dataset_url: Optional[str] = None
    session_local_path: Optional[str] = None
    session_dataset_id: Optional[str] = None
    has_active_data: bool = False
    question: Optional[str] = None
    # When True, skip session and go straight to registry (topic change)
    force_new_topic: bool = False

    def normalized_topic(self) -> str:
        return (self.topic or "").strip()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetRequest":
        if not isinstance(data, dict):
            raise ValueError("request must be a dict")
        topic = (data.get("topic") or "").strip()
        return cls(
            topic=topic,
            session_id=data.get("session_id"),
            session_topic=data.get("session_topic") or data.get("dataset_topic"),
            session_dataset_url=data.get("session_dataset_url") or data.get("dataset_url"),
            session_local_path=data.get("session_local_path")
            or data.get("local_path")
            or data.get("file_path")
            or data.get("dataset_path"),
            session_dataset_id=data.get("session_dataset_id") or data.get("dataset_id"),
            has_active_data=bool(data.get("has_active_data") or data.get("data") is not None),
            question=data.get("question"),
            force_new_topic=bool(data.get("force_new_topic") or data.get("topic_mismatch")),
        )


@dataclass
class ProviderHit:
    """Internal result from a single provider (before agent finalizes)."""

    status: RetrievalStatus
    dataset_id: Optional[str] = None
    local_path: Optional[str] = None
    download_url: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    reason: str = ""
    provider_name: str = ""


@dataclass
class RetrievalResult:
    """Final decision from Dataset Retrieval Agent."""

    status: RetrievalStatus
    dataset_id: Optional[str] = None
    local_path: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    reason: str = ""
    next_action: NextAction = NextAction.NONE
    download_url: Optional[str] = None
    provider: Optional[str] = None
    topic: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value if isinstance(self.status, RetrievalStatus) else self.status
        payload["next_action"] = (
            self.next_action.value if isinstance(self.next_action, NextAction) else self.next_action
        )
        return payload

    @classmethod
    def search_required(cls, topic: str, reason: str = "") -> "RetrievalResult":
        return cls(
            status=RetrievalStatus.SEARCH_REQUIRED,
            topic=topic,
            reason=reason or "No session or local registry dataset available; internet search required.",
            next_action=NextAction.RUN_INTERNET_SEARCH,
            provider=None,
            metadata=None,
        )
