"""Pydantic request/response schemas for session APIs (Phase 1 + Phase 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


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
    pinned: Optional[bool] = None
    status: Optional[Literal["active", "archived"]] = None


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)


class SessionFavoriteRequest(BaseModel):
    favorite: bool = True


class SessionPinRequest(BaseModel):
    pinned: bool = True
    pin_order: Optional[int] = Field(
        default=None,
        description="Optional sort rank among pinned sessions (lower = higher).",
    )


class SessionDuplicateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=512)
    include_messages: bool = True
    include_artifacts: bool = True


class SessionImportRequest(BaseModel):
    """Import a previously exported session bundle."""

    bundle: dict[str, Any] = Field(
        ...,
        description="Export payload from GET /sessions/{id}/export",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional new session id; generated if omitted.",
    )
    title: Optional[str] = Field(default=None, max_length=512)
    user_id: str = "anonymous"


# ---------------------------------------------------------------------------
# Nested entities
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    dataset_topic: Optional[str] = None
    status: str = "active"
    favorite: bool = False
    archived: bool = False
    deleted: bool = False
    pinned: bool = False
    pin_order: Optional[int] = None
    message_count: int = 0
    tags: list[str] = Field(default_factory=list)
    last_query: Optional[str] = None


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int
    sort_by: str = "updated_at"
    order: str = "desc"
    filters: dict[str, Any] = Field(default_factory=dict)


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
    pinned: bool = False
    pin_order: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    message_count: int = 0

    chat_history: list[MessageOut] = Field(default_factory=list)
    generated_charts: list[Any] = Field(default_factory=list)
    forecast_results: list[Any] = Field(default_factory=list)
    analysis_results: list[Any] = Field(default_factory=list)
    eda_outputs: list[Any] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)

    last_query: str = ""
    last_insight: str = ""
    last_column: str = ""
    last_columns: list[str] = Field(default_factory=list)
    last_chart_type: str = ""
    last_intent: str = ""
    last_operation: str = ""
    last_forecast_target: str = ""
    eda_summary: dict[str, Any] = Field(default_factory=dict)


class SessionExportBundle(BaseModel):
    format_version: str = "1.0"
    exported_at: str
    session: dict[str, Any]
    messages: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class SessionActionResponse(BaseModel):
    session_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    favorite: Optional[bool] = None
    archived: Optional[bool] = None
    deleted: Optional[bool] = None
    pinned: Optional[bool] = None
    pin_order: Optional[int] = None
    message: Optional[str] = None


class SessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool
    hard: bool = False


class SessionDuplicateResponse(SessionSummary):
    source_session_id: str


class SessionImportResponse(SessionSummary):
    imported: bool = True
    source_session_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    details: Optional[Any] = None
    code: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 4 — Search
# ---------------------------------------------------------------------------


class SearchHighlights(BaseModel):
    title: str = ""
    messages: str = ""
    summary: str = ""
    tags: str = ""


class SessionSearchHit(BaseModel):
    session_id: str
    title: str = ""
    rank: float = 0.0
    score: float = 0.0
    matched_fields: list[str] = Field(default_factory=list)
    highlights: SearchHighlights = Field(default_factory=SearchHighlights)
    snippet: str = ""
    status: str = "active"
    favorite: bool = False
    archived: bool = False
    deleted: bool = False
    pinned: bool = False
    dataset_topic: Optional[str] = None
    dataset_name: Optional[str] = None
    message_count: int = 0
    updated_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    last_query: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class SessionSearchResponse(BaseModel):
    query: str
    match_query: str = ""
    total: int
    limit: int
    offset: int
    engine: str = "fts5"  # fts5 | like | none
    items: list[SessionSearchHit] = Field(default_factory=list)
