"""SQLAlchemy models for durable analysis sessions (Phase 1).

Tables:
  - analysis_sessions  → AnalysisSession
  - session_messages   → SessionMessage
  - session_artifacts  → SessionArtifact
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from backend.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisSession(Base):
    """Primary session document: metadata + active dataset binding."""

    __tablename__ = "analysis_sessions"

    session_id = Column(String(128), primary_key=True, default=_uuid)
    user_id = Column(String(128), nullable=False, default="anonymous", index=True)

    title = Column(String(512), nullable=False, default="New analysis")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_activity_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Active dataset (denormalized for list/detail without joins)
    dataset_id = Column(String(128), nullable=True, index=True)
    dataset_name = Column(String(512), nullable=True)
    dataset_path = Column(String(2048), nullable=True)
    dataset_url = Column(String(2048), nullable=True)
    dataset_topic = Column(String(512), nullable=True)

    # Continuity fields (also dual-written to legacy session_memory)
    last_column = Column(String(256), nullable=True)
    last_columns = Column(JSON, nullable=True)
    last_chart_type = Column(String(64), nullable=True)
    last_intent = Column(String(128), nullable=True)
    last_operation = Column(String(128), nullable=True)
    last_forecast_target = Column(String(256), nullable=True)
    last_query = Column(Text, nullable=True)
    last_insight = Column(Text, nullable=True)
    eda_summary = Column(JSON, nullable=True)

    status = Column(String(32), nullable=False, default="active")  # active|archived|deleted
    favorite = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)
    deleted = Column(Boolean, nullable=False, default=False)

    message_count = Column(Integer, nullable=False, default=0)
    tags_json = Column(JSON, nullable=True)
    current_dataset = Column(JSON, nullable=True)
    last_used_columns = Column(JSON, nullable=True)

    messages = relationship(
        "SessionMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionMessage.seq",
        lazy="selectin",
    )
    artifacts = relationship(
        "SessionArtifact",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionArtifact.created_at",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_analysis_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_analysis_sessions_user_status", "user_id", "status", "updated_at"),
        Index("ix_analysis_sessions_deleted", "deleted"),
    )


class SessionMessage(Base):
    """Ordered chat history for one analysis session."""

    __tablename__ = "session_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(128),
        ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    role = Column(String(32), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Structured assistant payload refs / light metadata
    payload = Column(JSON, nullable=True)

    session = relationship("AnalysisSession", back_populates="messages")

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_session_msg_seq"),
        Index("ix_session_messages_session_seq", "session_id", "seq"),
    )


class SessionArtifact(Base):
    """Restorable analysis outputs: charts, forecasts, EDA, insights, etc."""

    __tablename__ = "session_artifacts"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(128),
        ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(
        String(36),
        ForeignKey("session_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # chart | forecast | eda | analysis_result | insight | hypothesis | profile
    kind = Column(String(32), nullable=False)
    title = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # JSON payload (Plotly figures, forecast series, EDA profiles, …)
    content = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    session = relationship("AnalysisSession", back_populates="artifacts")

    __table_args__ = (
        Index("ix_session_artifacts_session_kind", "session_id", "kind"),
    )
