"""Session Reliability v2 — durable SQLite transactions + read-after-write.

Guarantees:
  - Writers use BEGIN IMMEDIATE to serialize conflicting creates
  - Commits are flushed to the shared page cache before return
  - Post-commit verification sees the row from a fresh connection
  - Per-session locks eliminate concurrent create/ensure races
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from backend.core.logger import get_logger
from backend.db import SessionLocal, engine

logger = get_logger(__name__)

# Per-session mutexes (create / ensure / turn finalize)
_session_locks: dict[str, threading.RLock] = {}
_session_locks_guard = threading.Lock()

# Engine-level write lock for SQLite (single-writer friendliness under stress)
_write_lock = threading.RLock()

_sqlite_pragmas_applied = False
_pragma_lock = threading.Lock()


def session_lock(session_id: str) -> threading.RLock:
    sid = (session_id or "").strip() or "_empty"
    with _session_locks_guard:
        lock = _session_locks.get(sid)
        if lock is None:
            lock = threading.RLock()
            _session_locks[sid] = lock
        return lock


def configure_sqlite_durability() -> None:
    """Enable WAL + busy timeout so concurrent GET-after-CREATE is reliable."""
    global _sqlite_pragmas_applied
    with _pragma_lock:
        if _sqlite_pragmas_applied:
            return
        url = str(getattr(engine, "url", "") or "")
        if "sqlite" not in url.lower():
            _sqlite_pragmas_applied = True
            return
        try:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA busy_timeout=30000"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()
            _sqlite_pragmas_applied = True
            logger.info(
                "SQLite durability configured",
                extra={"journal_mode": "WAL", "busy_timeout_ms": 30000},
            )
        except Exception as exc:
            logger.warning(
                "SQLite durability pragmas failed",
                extra={"error": str(exc)},
            )
            _sqlite_pragmas_applied = True  # don't loop forever


@contextmanager
def write_session(*, begin_immediate: bool = True) -> Iterator[DbSession]:
    """
    Open a DB session, optionally BEGIN IMMEDIATE, auto commit/rollback.

    On success: commit once. On error: rollback. Always closes.
    """
    configure_sqlite_durability()
    db = SessionLocal()
    try:
        with _write_lock:
            if begin_immediate:
                try:
                    db.execute(text("BEGIN IMMEDIATE"))
                except Exception:
                    # Nested / non-sqlite — ignore; SQLAlchemy will begin on first op
                    pass
            yield db
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()


def commit_and_barrier(db: DbSession) -> None:
    """Commit the current transaction and ensure visibility for other connections."""
    db.commit()
    # Touch a fresh connection so WAL readers observe the latest frame promptly
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # Optional passive checkpoint — non-blocking
            try:
                conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            except Exception:
                pass
            conn.commit()
    except Exception as exc:
        logger.debug("Post-commit barrier skipped", extra={"error": str(exc)})


def verify_session_row(
    session_id: str,
    *,
    user_id: str | None = None,
    require_not_deleted: bool = True,
    retries: int = 5,
    delay_s: float = 0.02,
) -> dict[str, Any]:
    """
    Read-after-write verification using a fresh connection.

    Retries briefly to absorb rare SQLite visibility delays under load.
    Raises SessionNotFoundError-compatible RuntimeError if still missing.
    """
    from backend.sessions.models import AnalysisSession
    from backend.sessions.service import SessionAccessDenied, SessionNotFoundError

    configure_sqlite_durability()
    sid = (session_id or "").strip()
    if not sid:
        raise SessionNotFoundError(session_id or "")

    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == sid)
                .first()
            )
            if row is None:
                last_exc = SessionNotFoundError(sid)
            elif require_not_deleted and row.deleted:
                last_exc = SessionNotFoundError(sid)
            elif user_id is not None:
                owner = (user_id or "anonymous").strip() or "anonymous"
                if (row.user_id or "anonymous") != owner:
                    raise SessionAccessDenied(sid, owner)
                return {
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "title": row.title,
                    "deleted": bool(row.deleted),
                    "message_count": int(row.message_count or 0),
                    "dataset_path": row.dataset_path,
                    "dataset_topic": row.dataset_topic,
                    "verified": True,
                    "attempt": attempt + 1,
                }
            else:
                return {
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "title": row.title,
                    "deleted": bool(row.deleted),
                    "message_count": int(row.message_count or 0),
                    "dataset_path": row.dataset_path,
                    "dataset_topic": row.dataset_topic,
                    "verified": True,
                    "attempt": attempt + 1,
                }
        finally:
            db.close()
        time.sleep(delay_s * (attempt + 1))

    if last_exc:
        raise last_exc
    raise SessionNotFoundError(sid)


def finalize_session_write(
    session_id: str,
    *,
    user_id: str | None = None,
    expect_messages: bool = False,
) -> dict[str, Any]:
    """
    Barrier after create/turn: verify session (+ optional messages) are durable.

    Called before HTTP responses leave the process.
    """
    from backend.sessions.models import AnalysisSession, SessionMessage
    from backend.sessions.service import SessionNotFoundError

    info = verify_session_row(session_id, user_id=user_id)
    if expect_messages:
        db = SessionLocal()
        try:
            n = (
                db.query(SessionMessage)
                .filter(SessionMessage.session_id == session_id)
                .count()
            )
            info["message_rows"] = n
            if n <= 0:
                # One more retry cycle
                time.sleep(0.05)
                n = (
                    db.query(SessionMessage)
                    .filter(SessionMessage.session_id == session_id)
                    .count()
                )
                info["message_rows"] = n
            if n <= 0:
                raise SessionNotFoundError(session_id)
        finally:
            db.close()
    info["finalized"] = True
    return info
