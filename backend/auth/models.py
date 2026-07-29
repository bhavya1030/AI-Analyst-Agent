"""SQLAlchemy User model (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy import JSON

from backend.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """
    Application user for session ownership and multi-tenant isolation.

    ``id`` is the stable internal key stored on AnalysisSession.user_id.
    ``external_sub`` holds the JWT ``sub`` (or IdP subject) when linked.
    """

    __tablename__ = "users"

    id = Column(String(128), primary_key=True, default=_uuid)
    external_sub = Column(String(255), unique=True, nullable=True, index=True)
    email = Column(String(320), nullable=True, index=True)
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_anonymous = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Reserved for future profile / roles / JWT claim snapshot
    meta_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_users_active", "is_active"),
        Index("ix_users_anonymous", "is_anonymous"),
    )
