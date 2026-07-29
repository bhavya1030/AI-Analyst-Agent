"""User persistence and get-or-create helpers (Phase 8)."""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.auth.context import ANONYMOUS_USER_ID, AuthUser
from backend.auth.models import User
from backend.core.logger import get_logger
from backend.db import SessionLocal, engine

logger = get_logger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@\-]{1,128}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_auth_schema() -> None:
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        User.__table__.create(bind=engine, checkfirst=True)
        _ensure_anonymous_user()
        _schema_ready = True
        logger.info("Auth users table ready")


def _ensure_anonymous_user() -> None:
    db = SessionLocal()
    try:
        row = db.query(User).filter(User.id == ANONYMOUS_USER_ID).first()
        if row is None:
            db.add(
                User(
                    id=ANONYMOUS_USER_ID,
                    display_name="Anonymous",
                    is_anonymous=True,
                    is_active=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
            )
            db.commit()
            logger.info("Seeded anonymous user", extra={"user_id": ANONYMOUS_USER_ID})
    except Exception as exc:
        db.rollback()
        logger.warning("Anonymous user seed failed", extra={"error": str(exc)})
    finally:
        db.close()


def normalize_user_id(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ANONYMOUS_USER_ID
    if not _SAFE_ID.match(value):
        # Hash-like fallback for unsafe strings
        return f"user_{uuid.uuid5(uuid.NAMESPACE_URL, value).hex[:24]}"
    return value[:128]


class UserService:
    """CRUD-ish helpers for users; creates rows lazily on first sighting."""

    def __init__(self) -> None:
        ensure_auth_schema()

    def get(self, user_id: str) -> Optional[User]:
        ensure_auth_schema()
        db = SessionLocal()
        try:
            return (
                db.query(User)
                .filter(User.id == normalize_user_id(user_id))
                .first()
            )
        finally:
            db.close()

    def get_or_create(
        self,
        user_id: str | None = None,
        *,
        external_sub: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        is_anonymous: bool | None = None,
        claims: dict[str, Any] | None = None,
    ) -> User:
        ensure_auth_schema()
        uid = normalize_user_id(user_id or ANONYMOUS_USER_ID)
        db = SessionLocal()
        try:
            row = db.query(User).filter(User.id == uid).first()
            if row is None and external_sub:
                row = (
                    db.query(User)
                    .filter(User.external_sub == external_sub.strip())
                    .first()
                )
            if row is None:
                anon = uid == ANONYMOUS_USER_ID or bool(is_anonymous)
                row = User(
                    id=uid,
                    external_sub=(external_sub or None),
                    email=email,
                    display_name=display_name
                    or ("Anonymous" if anon else uid),
                    is_anonymous=anon,
                    is_active=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                    meta_json=claims or None,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                logger.info("User created", extra={"user_id": row.id})
            else:
                changed = False
                if external_sub and not row.external_sub:
                    row.external_sub = external_sub
                    changed = True
                if email and row.email != email:
                    row.email = email
                    changed = True
                if display_name and row.display_name != display_name:
                    row.display_name = display_name
                    changed = True
                if claims:
                    row.meta_json = {**(row.meta_json or {}), **claims}
                    changed = True
                if changed:
                    row.updated_at = _utcnow()
                    db.commit()
                    db.refresh(row)
            # Detach
            db.expunge(row)
            return row
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ensure_from_auth(self, auth: AuthUser) -> User:
        return self.get_or_create(
            auth.user_id,
            external_sub=auth.external_sub,
            email=auth.email,
            display_name=auth.display_name,
            is_anonymous=auth.is_anonymous,
            claims=auth.claims or None,
        )

    def list_users(self, *, limit: int = 100) -> list[dict[str, Any]]:
        ensure_auth_schema()
        db = SessionLocal()
        try:
            rows = (
                db.query(User)
                .order_by(User.created_at.desc())
                .limit(max(1, min(limit, 500)))
                .all()
            )
            return [
                {
                    "user_id": r.id,
                    "email": r.email,
                    "display_name": r.display_name,
                    "is_anonymous": bool(r.is_anonymous),
                    "is_active": bool(r.is_active),
                    "external_sub": r.external_sub,
                    "created_at": r.created_at.isoformat()
                    if isinstance(r.created_at, datetime)
                    else r.created_at,
                }
                for r in rows
            ]
        finally:
            db.close()


_service: UserService | None = None
_svc_lock = threading.Lock()


def get_user_service() -> UserService:
    global _service
    with _svc_lock:
        if _service is None:
            _service = UserService()
        return _service
