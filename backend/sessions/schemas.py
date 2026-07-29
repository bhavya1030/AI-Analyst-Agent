"""Pydantic request/response schemas for session APIs (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=512)
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional client-supplied id (e.g. session-1730…). Generated if omitted.",
    )
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_path: Optional[str] = None
    dataset_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    user_id: str = "anonymous"


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=512)
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_path: Optional[str] = None
    dataset_url: Optional[str] = None
    dataset_topic: Optional[str] = None
    tags: Optional[list[str]] = None
    favorite: Optional[bool] = None
    status: Optional[Literal["active", "archived"]] = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seq: int
    role: str
    content: str
    created_at: Optional[datetime] = None
    payload: Optional[dict[str, Any]] = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    content: Optional[Any] = None
    meta: Optional[dict[str, Any]] = None
    message_id: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_topic: Optional[str] = None
    status: str = "active"
    favorite: bool = False
    archived: bool = False
    deleted: bool = False
    message_count: int = 0
    tags: list[str] = Field(default_factory=list)
    last_query: Optional[str] = None


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseModel):
    """Full restore payload + legacy fields for the existing UI."""

    session_id: str
    title: str = "New analysis"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None

    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_path: str = ""
    dataset_url: str = ""
    dataset_topic: str = ""
    current_dataset: Optional[dict[str, Any]] = None
    last_used_columns: list[str] = Field(default_factory=list)

    status: str = "active"
    favorite: bool = False
    archived: bool = False
    deleted: bool = False
    tags: list[str] = Field(default_factory=list)
    message_count: int = 0

    # Full conversation + outputs (Phase 1 restore)
    chat_history: list[MessageOut] = Field(default_factory=list)
    generated_charts: list[Any] = Field(default_factory=list)
    forecast_results: list[Any] = Field(default_factory=list)
    analysis_results: list[Any] = Field(default_factory=list)
    eda_outputs: list[Any] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)

    # Legacy flat fields (UI SessionDetail / messagesFromDetail)
    last_query: str = ""
    last_insight: str = ""
    last_column: str = ""
    last_columns: list[str] = Field(default_factory=list)
    last_chart_type: str = ""
    last_intent: str = ""
    last_operation: str = ""
    last_forecast_target: str = ""
    eda_summary: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    details: Optional[Any] = None
    code: Optional[str] = None
