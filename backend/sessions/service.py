"""Session persistence service (Phase 1 + Phase 3).

Responsibilities:
  - CRUD for AnalysisSession
  - Append chat messages / artifacts
  - Dual-write to legacy session_memory
  - Phase 3: rename, archive, restore, pin, favorite, duplicate,
    export/import, recent, paginated list with sort + filters
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import asc, desc, inspect, or_, text
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from backend.core.logger import get_logger
from backend.db import SessionLocal, SessionMemory, engine
from backend.sessions.models import AnalysisSession, SessionArtifact, SessionMessage
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False

EXPORT_FORMAT_VERSION = "1.0"

# Columns that may be added after initial Phase-1 deploy (SQLite ALTER)
_PHASE3_COLUMNS: dict[str, str] = {
    "pinned": "BOOLEAN DEFAULT 0",
    "pin_order": "INTEGER",
    "conversation_summary": "TEXT",
}

SORTABLE_FIELDS = frozenset(
    {
        "updated_at",
        "created_at",
        "last_activity_at",
        "title",
        "message_count",
        "pin_order",
        "status",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_session_tables() -> None:
    """Create analysis_sessions / session_messages / session_artifacts if missing."""
    global _schema_ready
    with _schema_lock:
        if not _schema_ready:
            from backend.sessions import models as _models  # noqa: F401

            AnalysisSession.__table__.create(bind=engine, checkfirst=True)
            SessionMessage.__table__.create(bind=engine, checkfirst=True)
            SessionArtifact.__table__.create(bind=engine, checkfirst=True)
            _schema_ready = True
            logger.info("Session persistence tables ready")
        # Always reconcile Phase-3/4 columns (safe if already present)
        _ensure_phase3_columns()
        try:
            from backend.sessions.search import ensure_session_fts

            ensure_session_fts()
        except Exception as exc:
            logger.warning("Session FTS init skipped", extra={"error": str(exc)})


def _ensure_phase3_columns() -> None:
    """Add Phase-3 columns to existing SQLite tables (idempotent)."""
    try:
        with engine.begin() as connection:
            inspector = inspect(connection)
            if "analysis_sessions" not in inspector.get_table_names():
                return
            existing = {
                col["name"] for col in inspector.get_columns("analysis_sessions")
            }
            for name, col_type in _PHASE3_COLUMNS.items():
                if name in existing:
                    continue
                connection.execute(
                    text(f"ALTER TABLE analysis_sessions ADD COLUMN {name} {col_type}")
                )
                logger.info("Added analysis_sessions column", extra={"column": name})
    except Exception as exc:
        logger.warning(
            "Phase-3 column migration skipped",
            extra={"error": str(exc)},
        )


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session '{session_id}' not found")


class SessionService:
    """Production session store with legacy dual-write."""

    def __init__(self) -> None:
        ensure_session_tables()

    @staticmethod
    def _reindex(session_id: str) -> None:
        """Refresh FTS document for a session (best-effort)."""
        try:
            from backend.sessions.search import upsert_session_fts

            upsert_session_fts(session_id)
        except Exception as exc:
            logger.debug(
                "Session reindex skipped",
                extra={"session_id": session_id, "error": str(exc)},
            )

    @staticmethod
    def _drop_index(session_id: str) -> None:
        try:
            from backend.sessions.search import delete_session_fts

            delete_session_fts(session_id)
        except Exception as exc:
            logger.debug(
                "Session FTS delete skipped",
                extra={"session_id": session_id, "error": str(exc)},
            )

    def search_sessions(
        self,
        q: str,
        *,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        """Full-text search (Phase 4) — FTS5 with ranking + highlights."""
        ensure_session_tables()
        from backend.sessions.search import search_sessions_fts

        return search_sessions_fts(
            q,
            user_id=user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_session(
        self,
        *,
        title: str | None = None,
        session_id: str | None = None,
        dataset_id: str | None = None,
        dataset_name: str | None = None,
        dataset_path: str | None = None,
        dataset_url: str | None = None,
        tags: list[str] | None = None,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        ensure_session_tables()
        sid = (session_id or "").strip() or str(uuid.uuid4())
        now = _utcnow()
        resolved_title = (title or "").strip() or "New analysis"

        db = SessionLocal()
        try:
            existing = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == sid)
                .first()
            )
            if existing is not None:
                if existing.deleted:
                    # Re-open soft-deleted id as a fresh shell
                    existing.deleted = False
                    existing.archived = False
                    existing.status = "active"
                    existing.title = resolved_title
                    existing.updated_at = now
                    existing.last_activity_at = now
                    if dataset_id is not None:
                        existing.dataset_id = dataset_id
                    if dataset_name is not None:
                        existing.dataset_name = dataset_name
                    if dataset_path is not None:
                        existing.dataset_path = dataset_path
                    if dataset_url is not None:
                        existing.dataset_url = dataset_url
                    if tags is not None:
                        existing.tags_json = list(tags)
                    db.commit()
                    db.refresh(existing)
                    self._dual_write_legacy(db, existing)
                    self._reindex(sid)
                    return self._summary_dict(existing)

                # Idempotent create: return existing
                self._reindex(sid)
                return self._summary_dict(existing)

            row = AnalysisSession(
                session_id=sid,
                user_id=user_id or "anonymous",
                title=resolved_title,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                dataset_path=dataset_path,
                dataset_url=dataset_url,
                tags_json=list(tags or []),
                status="active",
                favorite=False,
                archived=False,
                deleted=False,
                pinned=False,
                pin_order=None,
                message_count=0,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            self._reindex(sid)
            logger.info("Session created", extra={"session_id": sid})
            return self._summary_dict(row)
        finally:
            db.close()

    def ensure_session(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
        title: str | None = None,
    ) -> AnalysisSession:
        """Get or create a session row. Migrates legacy SessionMemory if needed."""
        ensure_session_tables()
        sid = (session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")

        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == sid)
                .first()
            )
            if row is not None:
                if row.deleted:
                    row.deleted = False
                    row.status = "active"
                    row.updated_at = _utcnow()
                    db.commit()
                    db.refresh(row)
                return self._detach_copy(db, row)

            # Lazy-migrate from legacy flat table
            legacy = (
                db.query(SessionMemory)
                .filter(SessionMemory.session_id == sid)
                .first()
            )
            if legacy is not None:
                row = self._migrate_legacy(db, legacy, user_id=user_id)
                return self._detach_copy(db, row)

            now = _utcnow()
            row = AnalysisSession(
                session_id=sid,
                user_id=user_id or "anonymous",
                title=(title or "").strip() or "New analysis",
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                status="active",
                message_count=0,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            return self._detach_copy(db, row)
        finally:
            db.close()

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        include_deleted: bool = False,
        include_archived: bool = True,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        order: str = "desc",
        status: str | None = None,
        favorite: bool | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        tag: str | None = None,
        dataset_topic: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """
        Paginated session list with sorting and filtering (Phase 3).

        Sort: updated_at | created_at | last_activity_at | title | message_count | pin_order | status
        Filters: status, favorite, pinned, archived, tag, dataset_topic, free-text q
        Pinned sessions always surface first, then the chosen sort field.
        """
        ensure_session_tables()
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        sort_by = (sort_by or "updated_at").strip().lower()
        if sort_by not in SORTABLE_FIELDS:
            sort_by = "updated_at"
        order_dir = (order or "desc").strip().lower()
        if order_dir not in {"asc", "desc"}:
            order_dir = "desc"

        applied_filters: dict[str, Any] = {}

        db = SessionLocal()
        try:
            self._migrate_all_legacy(db, user_id=user_id)

            q_db = db.query(AnalysisSession)
            if user_id:
                q_db = q_db.filter(AnalysisSession.user_id == user_id)
                applied_filters["user_id"] = user_id

            # archived filter takes precedence over include_archived flag
            if archived is not None:
                q_db = q_db.filter(AnalysisSession.archived.is_(bool(archived)))
                applied_filters["archived"] = bool(archived)
            elif not include_archived:
                q_db = q_db.filter(AnalysisSession.archived.is_(False))
                applied_filters["include_archived"] = False

            if not include_deleted:
                q_db = q_db.filter(AnalysisSession.deleted.is_(False))
            else:
                applied_filters["include_deleted"] = True

            if status:
                status_norm = status.strip().lower()
                q_db = q_db.filter(AnalysisSession.status == status_norm)
                applied_filters["status"] = status_norm

            if favorite is not None:
                q_db = q_db.filter(AnalysisSession.favorite.is_(bool(favorite)))
                applied_filters["favorite"] = bool(favorite)

            if pinned is not None:
                q_db = q_db.filter(AnalysisSession.pinned.is_(bool(pinned)))
                applied_filters["pinned"] = bool(pinned)

            if dataset_topic:
                topic = dataset_topic.strip()
                q_db = q_db.filter(AnalysisSession.dataset_topic.ilike(f"%{topic}%"))
                applied_filters["dataset_topic"] = topic

            if tag:
                # JSON array membership differs across dialects; apply in Python below.
                applied_filters["tag"] = tag.strip()

            if q:
                query_text = q.strip()
                like = f"%{query_text}%"
                q_db = q_db.filter(
                    or_(
                        AnalysisSession.title.ilike(like),
                        AnalysisSession.last_query.ilike(like),
                        AnalysisSession.dataset_topic.ilike(like),
                        AnalysisSession.dataset_name.ilike(like),
                    )
                )
                applied_filters["q"] = query_text

            # Ordering: pinned first, then sort field
            sort_column = getattr(AnalysisSession, sort_by, AnalysisSession.updated_at)
            primary = desc(sort_column) if order_dir == "desc" else asc(sort_column)
            # pin_order: lower numbers first among pinned; nulls last via secondary updated_at
            pin_order_col = asc(AnalysisSession.pin_order)
            order_clauses = [
                desc(AnalysisSession.pinned),
                pin_order_col,
                primary,
            ]

            # Tag filter requires materialization for SQLite JSON portability
            if tag:
                all_rows = q_db.order_by(*order_clauses).all()
                tag_clean = tag.strip().lower()
                filtered = [
                    r
                    for r in all_rows
                    if any(
                        str(t).lower() == tag_clean for t in (r.tags_json or [])
                    )
                ]
                total = len(filtered)
                rows = filtered[offset : offset + limit]
            else:
                total = q_db.count()
                rows = (
                    q_db.order_by(*order_clauses).offset(offset).limit(limit).all()
                )

            return {
                "items": [self._summary_dict(r) for r in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "order": order_dir,
                "filters": applied_filters,
            }
        finally:
            db.close()

    def list_session_ids(self, *, include_deleted: bool = False) -> list[str]:
        """Backward-compatible flat list of session ids (UI expects string[])."""
        ensure_session_tables()
        db = SessionLocal()
        try:
            self._migrate_all_legacy(db)

            q = db.query(AnalysisSession.session_id)
            if not include_deleted:
                q = q.filter(AnalysisSession.deleted.is_(False))
            ids = [r[0] for r in q.order_by(AnalysisSession.updated_at.desc()).all()]

            # Union any legacy ids not yet migrated (paranoia)
            legacy_ids = [r[0] for r in db.query(SessionMemory.session_id).all()]
            for lid in legacy_ids:
                if lid not in ids:
                    ids.append(lid)
            return ids
        finally:
            db.close()

    def get_session_detail(
        self,
        session_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        ensure_session_tables()
        sid = (session_id or "").strip()
        if not sid:
            raise SessionNotFoundError(session_id or "")

        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisSession)
                .options(
                    selectinload(AnalysisSession.messages),
                    selectinload(AnalysisSession.artifacts),
                )
                .filter(AnalysisSession.session_id == sid)
                .first()
            )

            if row is None:
                legacy = (
                    db.query(SessionMemory)
                    .filter(SessionMemory.session_id == sid)
                    .first()
                )
                if legacy is None:
                    raise SessionNotFoundError(sid)
                row = self._migrate_legacy(db, legacy)
                row = (
                    db.query(AnalysisSession)
                    .options(
                        selectinload(AnalysisSession.messages),
                        selectinload(AnalysisSession.artifacts),
                    )
                    .filter(AnalysisSession.session_id == sid)
                    .first()
                )

            if row is None:
                raise SessionNotFoundError(sid)
            if row.deleted and not include_deleted:
                raise SessionNotFoundError(sid)

            return self._detail_dict(row)
        finally:
            db.close()

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        dataset_id: str | None = None,
        dataset_name: str | None = None,
        dataset_path: str | None = None,
        dataset_url: str | None = None,
        dataset_topic: str | None = None,
        tags: list[str] | None = None,
        favorite: bool | None = None,
        pinned: bool | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=True)
            if title is not None:
                cleaned = title.strip()
                if cleaned:
                    row.title = cleaned
            if dataset_id is not None:
                row.dataset_id = dataset_id
            if dataset_name is not None:
                row.dataset_name = dataset_name
            if dataset_path is not None:
                row.dataset_path = dataset_path
            if dataset_url is not None:
                row.dataset_url = dataset_url
            if dataset_topic is not None:
                row.dataset_topic = dataset_topic
            if tags is not None:
                row.tags_json = list(tags)
            if favorite is not None:
                row.favorite = bool(favorite)
            if pinned is not None:
                row.pinned = bool(pinned)
                if not row.pinned:
                    row.pin_order = None
            if status is not None:
                if status == "archived":
                    row.archived = True
                    row.deleted = False
                    row.status = "archived"
                elif status == "active":
                    row.archived = False
                    row.deleted = False
                    row.status = "active"
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            self._reindex(session_id)
            return self._summary_dict(row)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Phase 3 — lifecycle & organization
    # ------------------------------------------------------------------

    def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValueError("title must be non-empty")
        result = self.update_session(session_id, title=cleaned)
        self._reindex(session_id)
        return result

    def archive_session(self, session_id: str) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=False)
            row.archived = True
            row.deleted = False
            row.status = "archived"
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            logger.info("Session archived", extra={"session_id": session_id})
            return self._summary_dict(row)
        finally:
            db.close()

    def restore_session(self, session_id: str) -> dict[str, Any]:
        """Unarchive and/or undelete a session back to active."""
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=True)
            row.archived = False
            row.deleted = False
            row.status = "active"
            row.updated_at = _utcnow()
            row.last_activity_at = row.updated_at
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            logger.info("Session restored", extra={"session_id": session_id})
            return self._summary_dict(row)
        finally:
            db.close()

    def set_favorite(self, session_id: str, favorite: bool = True) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=False)
            row.favorite = bool(favorite)
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            return self._summary_dict(row)
        finally:
            db.close()

    def set_pinned(
        self,
        session_id: str,
        pinned: bool = True,
        *,
        pin_order: int | None = None,
    ) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=False)
            row.pinned = bool(pinned)
            if row.pinned:
                if pin_order is not None:
                    row.pin_order = int(pin_order)
                elif row.pin_order is None:
                    # Append to end of pin stack
                    max_order = (
                        db.query(AnalysisSession.pin_order)
                        .filter(
                            AnalysisSession.user_id == row.user_id,
                            AnalysisSession.pinned.is_(True),
                            AnalysisSession.pin_order.isnot(None),
                        )
                        .order_by(desc(AnalysisSession.pin_order))
                        .first()
                    )
                    row.pin_order = int(max_order[0]) + 1 if max_order and max_order[0] is not None else 0
            else:
                row.pin_order = None
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            return self._summary_dict(row)
        finally:
            db.close()

    def duplicate_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        include_messages: bool = True,
        include_artifacts: bool = True,
    ) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            source = (
                db.query(AnalysisSession)
                .options(
                    selectinload(AnalysisSession.messages),
                    selectinload(AnalysisSession.artifacts),
                )
                .filter(AnalysisSession.session_id == session_id)
                .first()
            )
            if source is None or source.deleted:
                raise SessionNotFoundError(session_id)

            now = _utcnow()
            new_id = str(uuid.uuid4())
            new_title = (title or "").strip() or f"Copy of {source.title or 'session'}"

            clone = AnalysisSession(
                session_id=new_id,
                user_id=source.user_id or "anonymous",
                title=new_title[:512],
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                dataset_id=source.dataset_id,
                dataset_name=source.dataset_name,
                dataset_path=source.dataset_path,
                dataset_url=source.dataset_url,
                dataset_topic=source.dataset_topic,
                last_column=source.last_column,
                last_columns=source.last_columns,
                last_chart_type=source.last_chart_type,
                last_intent=source.last_intent,
                last_operation=source.last_operation,
                last_forecast_target=source.last_forecast_target,
                last_query=source.last_query,
                last_insight=source.last_insight,
                eda_summary=source.eda_summary,
                status="active",
                favorite=False,
                archived=False,
                deleted=False,
                pinned=False,
                pin_order=None,
                message_count=0,
                tags_json=list(source.tags_json or []),
                current_dataset=source.current_dataset,
                last_used_columns=source.last_used_columns,
            )
            db.add(clone)
            db.flush()

            msg_id_map: dict[str, str] = {}
            if include_messages:
                for msg in sorted(source.messages or [], key=lambda m: m.seq or 0):
                    new_msg_id = str(uuid.uuid4())
                    msg_id_map[msg.id] = new_msg_id
                    db.add(
                        SessionMessage(
                            id=new_msg_id,
                            session_id=new_id,
                            seq=msg.seq,
                            role=msg.role,
                            content=msg.content or "",
                            created_at=msg.created_at or now,
                            payload=msg.payload,
                        )
                    )
                clone.message_count = len(msg_id_map)

            if include_artifacts:
                for art in source.artifacts or []:
                    new_msg_ref = None
                    if art.message_id and art.message_id in msg_id_map:
                        new_msg_ref = msg_id_map[art.message_id]
                    db.add(
                        SessionArtifact(
                            id=str(uuid.uuid4()),
                            session_id=new_id,
                            message_id=new_msg_ref,
                            kind=art.kind,
                            title=art.title,
                            created_at=art.created_at or now,
                            content=art.content,
                            meta=art.meta,
                        )
                    )

            db.commit()
            db.refresh(clone)
            self._dual_write_legacy(db, clone)
            self._reindex(new_id)
            summary = self._summary_dict(clone)
            summary["source_session_id"] = session_id
            logger.info(
                "Session duplicated",
                extra={"source": session_id, "session_id": new_id},
            )
            return summary
        finally:
            db.close()

    def export_session(self, session_id: str) -> dict[str, Any]:
        ensure_session_tables()
        detail = self.get_session_detail(session_id, include_deleted=True)
        messages = detail.get("chat_history") or []
        artifacts = detail.get("artifacts") or []
        session_meta = {
            k: detail.get(k)
            for k in (
                "session_id",
                "title",
                "created_at",
                "updated_at",
                "last_activity_at",
                "dataset_id",
                "dataset_name",
                "dataset_path",
                "dataset_url",
                "dataset_topic",
                "current_dataset",
                "last_used_columns",
                "status",
                "favorite",
                "archived",
                "deleted",
                "pinned",
                "pin_order",
                "tags",
                "message_count",
                "last_query",
                "last_insight",
                "last_column",
                "last_columns",
                "last_chart_type",
                "last_intent",
                "last_operation",
                "last_forecast_target",
                "eda_summary",
            )
        }
        return sanitize_for_json(
            {
                "format_version": EXPORT_FORMAT_VERSION,
                "exported_at": _utcnow().isoformat(),
                "session": session_meta,
                "messages": messages,
                "artifacts": artifacts,
            }
        )

    def import_session(
        self,
        bundle: dict[str, Any],
        *,
        session_id: str | None = None,
        title: str | None = None,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        ensure_session_tables()
        if not isinstance(bundle, dict):
            raise ValueError("bundle must be an object")

        session_meta = bundle.get("session") or {}
        if not isinstance(session_meta, dict):
            session_meta = {}
        messages = bundle.get("messages") or []
        artifacts = bundle.get("artifacts") or []
        if not isinstance(messages, list):
            messages = []
        if not isinstance(artifacts, list):
            artifacts = []

        now = _utcnow()
        new_id = (session_id or "").strip() or str(uuid.uuid4())
        source_id = session_meta.get("session_id")
        resolved_title = (
            (title or "").strip()
            or str(session_meta.get("title") or "").strip()
            or "Imported session"
        )

        db = SessionLocal()
        try:
            existing = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == new_id)
                .first()
            )
            if existing is not None:
                raise ValueError(f"session_id '{new_id}' already exists")

            row = AnalysisSession(
                session_id=new_id,
                user_id=user_id or "anonymous",
                title=resolved_title[:512],
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                dataset_id=session_meta.get("dataset_id"),
                dataset_name=session_meta.get("dataset_name"),
                dataset_path=session_meta.get("dataset_path") or None,
                dataset_url=session_meta.get("dataset_url") or None,
                dataset_topic=session_meta.get("dataset_topic") or None,
                last_column=session_meta.get("last_column") or None,
                last_columns=session_meta.get("last_columns"),
                last_chart_type=session_meta.get("last_chart_type") or None,
                last_intent=session_meta.get("last_intent") or None,
                last_operation=session_meta.get("last_operation") or None,
                last_forecast_target=session_meta.get("last_forecast_target") or None,
                last_query=session_meta.get("last_query") or None,
                last_insight=session_meta.get("last_insight") or None,
                eda_summary=session_meta.get("eda_summary") or None,
                status="active",
                favorite=bool(session_meta.get("favorite")),
                archived=False,
                deleted=False,
                pinned=bool(session_meta.get("pinned")),
                pin_order=session_meta.get("pin_order"),
                message_count=0,
                tags_json=list(session_meta.get("tags") or []),
                current_dataset=session_meta.get("current_dataset"),
                last_used_columns=session_meta.get("last_used_columns"),
            )
            db.add(row)
            db.flush()

            msg_id_map: dict[str, str] = {}
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                old_id = str(msg.get("id") or "")
                new_msg_id = str(uuid.uuid4())
                if old_id:
                    msg_id_map[old_id] = new_msg_id
                seq = msg.get("seq")
                if seq is None:
                    seq = idx + 1
                db.add(
                    SessionMessage(
                        id=new_msg_id,
                        session_id=new_id,
                        seq=int(seq),
                        role=str(msg.get("role") or "assistant"),
                        content=str(msg.get("content") or ""),
                        created_at=now,
                        payload=msg.get("payload"),
                    )
                )
            row.message_count = len(msg_id_map) if msg_id_map else len(
                [m for m in messages if isinstance(m, dict)]
            )

            for art in artifacts:
                if not isinstance(art, dict):
                    continue
                old_msg = art.get("message_id")
                new_msg_ref = msg_id_map.get(str(old_msg)) if old_msg else None
                db.add(
                    SessionArtifact(
                        id=str(uuid.uuid4()),
                        session_id=new_id,
                        message_id=new_msg_ref,
                        kind=str(art.get("kind") or "analysis_result"),
                        title=art.get("title"),
                        created_at=now,
                        content=art.get("content"),
                        meta=art.get("meta"),
                    )
                )

            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            self._reindex(new_id)
            summary = self._summary_dict(row)
            summary["imported"] = True
            summary["source_session_id"] = source_id
            logger.info(
                "Session imported",
                extra={"session_id": new_id, "source_session_id": source_id},
            )
            return summary
        finally:
            db.close()

    def recent_sessions(
        self,
        *,
        user_id: str | None = None,
        limit: int = 10,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """Most recently active non-deleted sessions (pinned still sort first)."""
        return self.list_sessions(
            user_id=user_id,
            include_deleted=False,
            include_archived=include_archived,
            limit=limit,
            offset=0,
            sort_by="last_activity_at",
            order="desc",
        )

    def delete_session(self, session_id: str, *, hard: bool = False) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.session_id == session_id)
                .first()
            )
            if row is None:
                # Soft-delete / remove legacy-only
                legacy = (
                    db.query(SessionMemory)
                    .filter(SessionMemory.session_id == session_id)
                    .first()
                )
                if legacy is None:
                    raise SessionNotFoundError(session_id)
                if hard:
                    db.delete(legacy)
                    db.commit()
                else:
                    # Create tombstone session then soft-delete
                    row = self._migrate_legacy(db, legacy)
                    row.deleted = True
                    row.status = "deleted"
                    row.updated_at = _utcnow()
                    db.commit()
                return {"session_id": session_id, "deleted": True, "hard": hard}

            if hard:
                sid = row.session_id
                db.delete(row)
                legacy = (
                    db.query(SessionMemory)
                    .filter(SessionMemory.session_id == sid)
                    .first()
                )
                if legacy is not None:
                    db.delete(legacy)
                db.commit()
                self._drop_index(sid)
                return {"session_id": sid, "deleted": True, "hard": True}

            row.deleted = True
            row.status = "deleted"
            row.updated_at = _utcnow()
            db.commit()
            # Keep FTS doc for soft-delete so search can exclude via join filters;
            # hard delete removes the FTS row above.
            return {"session_id": row.session_id, "deleted": True, "hard": False}
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Turn persistence (/ask)
    # ------------------------------------------------------------------

    def append_user_message(
        self,
        session_id: str,
        content: str,
        *,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        ensure_session_tables()
        self.ensure_session(session_id, user_id=user_id)

        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=False)
            seq = self._next_seq(db, session_id)
            msg = SessionMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                seq=seq,
                role="user",
                content=content or "",
                created_at=_utcnow(),
                payload=None,
            )
            db.add(msg)

            row.message_count = int(row.message_count or 0) + 1
            row.last_query = content or ""
            row.updated_at = _utcnow()
            row.last_activity_at = row.updated_at
            if not row.title or row.title == "New analysis":
                preview = (content or "").strip().replace("\n", " ")
                if preview:
                    row.title = preview[:72] + ("…" if len(preview) > 72 else "")

            db.commit()
            db.refresh(msg)
            self._dual_write_legacy(db, row)
            self._reindex(session_id)
            return {
                "id": msg.id,
                "seq": msg.seq,
                "role": msg.role,
                "content": msg.content,
            }
        finally:
            db.close()

    def record_assistant_turn(
        self,
        session_id: str,
        *,
        question: str,
        result: dict[str, Any],
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Persist assistant message + artifacts after a successful graph run.
        Also dual-writes legacy session_memory fields.
        """
        ensure_session_tables()
        self.ensure_session(session_id)

        safe_result = self._sanitize_graph_result(result)

        answer = str(safe_result.get("answer") or "")
        now = _utcnow()

        db = SessionLocal()
        try:
            row = self._require_row(db, session_id, allow_deleted=False)

            # --- dataset binding ---
            self._apply_dataset_from_result(row, safe_result, file_path=file_path)

            # continuity fields
            if safe_result.get("last_column_used") is not None:
                row.last_column = safe_result.get("last_column_used")
            cols = safe_result.get("last_columns_used") or safe_result.get("columns") or []
            if cols:
                row.last_columns = list(cols) if isinstance(cols, list) else cols
                row.last_used_columns = list(row.last_columns or [])
            if safe_result.get("last_chart_type") is not None:
                row.last_chart_type = safe_result.get("last_chart_type")
            if safe_result.get("last_intent") is not None:
                row.last_intent = safe_result.get("last_intent")
            if safe_result.get("last_operation") is not None:
                row.last_operation = safe_result.get("last_operation")
            if safe_result.get("last_forecast_target") is not None:
                row.last_forecast_target = safe_result.get("last_forecast_target")
            if safe_result.get("dataset_topic") is not None:
                row.dataset_topic = safe_result.get("dataset_topic")
                if not row.dataset_name:
                    row.dataset_name = safe_result.get("dataset_topic")

            profile = safe_result.get("dataset_profile") or {}
            if profile:
                row.eda_summary = profile

            row.last_query = question or row.last_query
            row.last_insight = answer
            # Keep conversation_summary fresh for FTS (lightweight rolling digest)
            if answer:
                prev = (row.conversation_summary or "").strip()
                digest = answer.strip()[:500]
                row.conversation_summary = (
                    f"{prev}\n{digest}".strip()[-2000:] if prev else digest
                )
            row.updated_at = now
            row.last_activity_at = now

            # --- assistant message ---
            seq = self._next_seq(db, session_id)
            msg_id = str(uuid.uuid4())
            artifact_ids: list[str] = []

            # Build artifacts first so message payload can reference them
            artifacts = self._build_artifacts_from_result(
                session_id=session_id,
                message_id=msg_id,
                result=safe_result,
                now=now,
            )
            for art in artifacts:
                db.add(art)
                artifact_ids.append(art.id)

            payload = {
                "artifact_ids": artifact_ids,
                "intent": safe_result.get("last_intent"),
                "operation": safe_result.get("last_operation"),
                "dataset_topic": safe_result.get("dataset_topic"),
                "chart_columns_used": safe_result.get("chart_columns_used") or [],
                "has_charts": bool(safe_result.get("charts") or safe_result.get("chart")),
                "has_forecast": bool(
                    safe_result.get("forecast") or safe_result.get("forecast_chart")
                ),
            }

            msg = SessionMessage(
                id=msg_id,
                session_id=session_id,
                seq=seq,
                role="assistant",
                content=answer,
                created_at=now,
                payload=payload,
            )
            db.add(msg)
            row.message_count = int(row.message_count or 0) + 1

            db.commit()
            db.refresh(msg)
            self._dual_write_legacy(db, row)
            self._reindex(session_id)

            logger.info(
                "Assistant turn persisted",
                extra={
                    "session_id": session_id,
                    "message_id": msg_id,
                    "artifact_count": len(artifact_ids),
                },
            )
            return {
                "message_id": msg_id,
                "seq": seq,
                "artifact_ids": artifact_ids,
            }
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_row(
        self,
        db: DbSession,
        session_id: str,
        *,
        allow_deleted: bool = False,
    ) -> AnalysisSession:
        row = (
            db.query(AnalysisSession)
            .filter(AnalysisSession.session_id == session_id)
            .first()
        )
        if row is None:
            raise SessionNotFoundError(session_id)
        if row.deleted and not allow_deleted:
            raise SessionNotFoundError(session_id)
        return row

    def _next_seq(self, db: DbSession, session_id: str) -> int:
        last = (
            db.query(SessionMessage.seq)
            .filter(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.seq.desc())
            .first()
        )
        return int(last[0]) + 1 if last else 1

    @staticmethod
    def _sanitize_graph_result(result: dict[str, Any] | None) -> dict[str, Any]:
        """JSON-safe graph result without DataFrames or other non-persistable blobs."""
        if not result or not isinstance(result, dict):
            return {}

        skip = {
            "data",
            "last_dataset",
            "dataframe",
            "df",
            "merged_dataframe",
        }
        slim: dict[str, Any] = {}
        for key, value in result.items():
            if key in skip:
                continue
            type_name = type(value).__name__
            if type_name in {"DataFrame", "Series"}:
                continue
            slim[key] = value

        # Preserve row/column counts if present or inferable without storing frames
        if "rows" not in slim and result.get("data") is not None:
            try:
                slim["rows"] = int(result["data"].shape[0])  # type: ignore[union-attr]
            except Exception:
                pass
        if "columns" not in slim and result.get("data") is not None:
            try:
                slim["columns"] = list(result["data"].columns)  # type: ignore[union-attr]
            except Exception:
                pass

        cleaned = sanitize_for_json(slim)
        return cleaned if isinstance(cleaned, dict) else {}

    def _apply_dataset_from_result(
        self,
        row: AnalysisSession,
        result: dict[str, Any],
        *,
        file_path: str | None,
    ) -> None:
        dataset_url = result.get("dataset_url") or None
        local_path = result.get("local_path") or result.get("file_path") or None
        dataset_id = result.get("dataset_id") or result.get("registry_id") or None
        topic = result.get("dataset_topic") or None

        has_frame = (
            result.get("data") is not None
            or result.get("rows") is not None
            or bool(result.get("columns"))
        )

        if file_path:
            if str(file_path).startswith(("http://", "https://")):
                row.dataset_url = str(file_path)
                row.dataset_path = None
            else:
                # Prefer local upload path when provided and data loaded
                if has_frame:
                    row.dataset_path = str(file_path)
                    if not dataset_url:
                        row.dataset_url = None

        if dataset_url and (has_frame or not file_path):
            # Graph discovered a remote dataset
            if not file_path or str(file_path).startswith(("http://", "https://")):
                row.dataset_url = str(dataset_url)
                if not local_path:
                    row.dataset_path = None

        if local_path and not str(local_path).startswith(("http://", "https://")):
            if has_frame:
                row.dataset_path = row.dataset_path or str(local_path)

        if dataset_id:
            row.dataset_id = str(dataset_id)
        if topic:
            row.dataset_topic = topic
            if not row.dataset_name:
                row.dataset_name = topic

        row.current_dataset = sanitize_for_json(
            {
                "dataset_id": row.dataset_id,
                "dataset_name": row.dataset_name,
                "dataset_path": row.dataset_path,
                "dataset_url": row.dataset_url,
                "dataset_topic": row.dataset_topic,
                "columns": result.get("columns") or row.last_columns or [],
                "rows": result.get("rows") or 0,
                "source": result.get("source") or result.get("dataset_source"),
            }
        )

    def _build_artifacts_from_result(
        self,
        *,
        session_id: str,
        message_id: str,
        result: dict[str, Any],
        now: datetime,
    ) -> list[SessionArtifact]:
        arts: list[SessionArtifact] = []

        # Charts
        charts = result.get("charts") or []
        if not charts and result.get("chart"):
            chart = result.get("chart")
            if chart:
                charts = [chart]
        for idx, chart in enumerate(charts):
            if not chart:
                continue
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="chart",
                    title=f"Chart {idx + 1}",
                    created_at=now,
                    content=chart,
                    meta={
                        "index": idx,
                        "chart_type": result.get("last_chart_type"),
                        "columns_used": result.get("chart_columns_used") or [],
                    },
                )
            )

        # Forecast
        forecast_values = result.get("forecast") or []
        forecast_chart = result.get("forecast_chart")
        if forecast_values or forecast_chart:
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="forecast",
                    title="Forecast",
                    created_at=now,
                    content={
                        "values": forecast_values,
                        "chart": forecast_chart or {},
                        "error": result.get("forecast_error") or "",
                    },
                    meta={
                        "target": result.get("last_forecast_target"),
                    },
                )
            )

        # EDA / profile
        profile = result.get("dataset_profile") or {}
        if profile:
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="eda",
                    title="EDA summary",
                    created_at=now,
                    content=profile,
                    meta={"source": "dataset_profile"},
                )
            )

        # Analysis / insights bundle
        insights = result.get("insights") or []
        patterns = result.get("detected_patterns") or []
        explanation = result.get("dataset_explanation") or []
        hypotheses = result.get("hypotheses") or []
        recommendations = result.get("recommended_next_steps") or []
        chart_explanation = result.get("chart_explanation") or ""

        if any([insights, patterns, explanation, hypotheses, recommendations, chart_explanation]):
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="analysis_result",
                    title="Analysis results",
                    created_at=now,
                    content={
                        "insights": insights,
                        "detected_patterns": patterns,
                        "dataset_explanation": explanation,
                        "hypotheses": hypotheses,
                        "recommended_next_steps": recommendations,
                        "chart_explanation": chart_explanation,
                        "answer": result.get("answer") or "",
                    },
                    meta={
                        "intent": result.get("last_intent"),
                        "operation": result.get("last_operation"),
                    },
                )
            )

        if result.get("answer"):
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="insight",
                    title="Insight",
                    created_at=now,
                    content={"text": result.get("answer")},
                    meta=None,
                )
            )

        if hypotheses:
            arts.append(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    kind="hypothesis",
                    title="Hypotheses",
                    created_at=now,
                    content={"hypotheses": hypotheses},
                    meta=None,
                )
            )

        return arts

    def _migrate_legacy(
        self,
        db: DbSession,
        legacy: SessionMemory,
        *,
        user_id: str = "anonymous",
    ) -> AnalysisSession:
        now = _utcnow()
        sid = legacy.session_id
        existing = (
            db.query(AnalysisSession)
            .filter(AnalysisSession.session_id == sid)
            .first()
        )
        if existing is not None:
            return existing

        title = "New analysis"
        if legacy.last_query:
            preview = str(legacy.last_query).strip().replace("\n", " ")
            title = preview[:72] + ("…" if len(preview) > 72 else "")
        elif legacy.dataset_topic:
            title = str(legacy.dataset_topic)[:72]

        row = AnalysisSession(
            session_id=sid,
            user_id=user_id or "anonymous",
            title=title,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            dataset_path=legacy.dataset_path,
            dataset_url=legacy.dataset_url,
            dataset_topic=legacy.dataset_topic,
            dataset_name=legacy.dataset_topic,
            last_column=legacy.last_column,
            last_columns=legacy.last_columns,
            last_used_columns=legacy.last_columns,
            last_chart_type=legacy.last_chart_type,
            last_intent=legacy.last_intent,
            last_operation=legacy.last_operation,
            last_forecast_target=legacy.last_forecast_target,
            last_query=legacy.last_query,
            last_insight=legacy.last_insight,
            eda_summary=legacy.eda_summary,
            status="active",
            message_count=0,
            current_dataset={
                "dataset_path": legacy.dataset_path,
                "dataset_url": legacy.dataset_url,
                "dataset_topic": legacy.dataset_topic,
            },
        )
        db.add(row)
        db.flush()

        seq = 1
        if legacy.last_query:
            db.add(
                SessionMessage(
                    id=str(uuid.uuid4()),
                    session_id=sid,
                    seq=seq,
                    role="user",
                    content=str(legacy.last_query),
                    created_at=now,
                )
            )
            seq += 1
        if legacy.last_insight:
            msg_id = str(uuid.uuid4())
            db.add(
                SessionMessage(
                    id=msg_id,
                    session_id=sid,
                    seq=seq,
                    role="assistant",
                    content=str(legacy.last_insight),
                    created_at=now,
                    payload={},
                )
            )
            if legacy.eda_summary:
                db.add(
                    SessionArtifact(
                        id=str(uuid.uuid4()),
                        session_id=sid,
                        message_id=msg_id,
                        kind="eda",
                        title="EDA summary",
                        created_at=now,
                        content=legacy.eda_summary,
                        meta={"migrated": True},
                    )
                )
            db.add(
                SessionArtifact(
                    id=str(uuid.uuid4()),
                    session_id=sid,
                    message_id=msg_id,
                    kind="insight",
                    title="Insight",
                    created_at=now,
                    content={"text": legacy.last_insight},
                    meta={"migrated": True},
                )
            )
            seq += 1

        row.message_count = seq - 1
        db.commit()
        db.refresh(row)
        logger.info("Migrated legacy session_memory row", extra={"session_id": sid})
        return row

    def _migrate_all_legacy(
        self, db: DbSession, *, user_id: str | None = None
    ) -> int:
        existing_ids = {
            r[0] for r in db.query(AnalysisSession.session_id).all()
        }
        legacy_rows = db.query(SessionMemory).all()
        count = 0
        for legacy in legacy_rows:
            if legacy.session_id in existing_ids:
                continue
            self._migrate_legacy(db, legacy, user_id=user_id or "anonymous")
            count += 1
        return count

    def _dual_write_legacy(self, db: DbSession, row: AnalysisSession) -> None:
        """Keep session_memory in sync so old get_session/save_session still work."""
        try:
            legacy = (
                db.query(SessionMemory)
                .filter(SessionMemory.session_id == row.session_id)
                .first()
            )
            if legacy is None:
                legacy = SessionMemory(session_id=row.session_id)
                db.add(legacy)
            legacy.dataset_path = row.dataset_path
            legacy.dataset_url = row.dataset_url
            legacy.dataset_topic = row.dataset_topic
            legacy.last_column = row.last_column
            legacy.last_columns = row.last_columns
            legacy.last_chart_type = row.last_chart_type
            legacy.last_intent = row.last_intent
            legacy.last_operation = row.last_operation
            legacy.last_forecast_target = row.last_forecast_target
            legacy.last_query = row.last_query
            legacy.last_insight = row.last_insight
            legacy.eda_summary = row.eda_summary
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Legacy dual-write failed",
                extra={"session_id": row.session_id, "error": str(exc)},
            )

    def _summary_dict(self, row: AnalysisSession) -> dict[str, Any]:
        return sanitize_for_json(
            {
                "session_id": row.session_id,
                "title": row.title or "New analysis",
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "last_activity_at": row.last_activity_at,
                "dataset_id": row.dataset_id,
                "dataset_name": row.dataset_name,
                "dataset_topic": row.dataset_topic,
                "status": row.status or "active",
                "favorite": bool(row.favorite),
                "archived": bool(row.archived),
                "deleted": bool(row.deleted),
                "pinned": bool(getattr(row, "pinned", False)),
                "pin_order": getattr(row, "pin_order", None),
                "message_count": int(row.message_count or 0),
                "tags": list(row.tags_json or []),
                "last_query": row.last_query,
                "conversation_summary": getattr(row, "conversation_summary", None),
            }
        )

    def _detail_dict(self, row: AnalysisSession) -> dict[str, Any]:
        messages = sorted(row.messages or [], key=lambda m: m.seq or 0)
        artifacts = list(row.artifacts or [])

        charts: list[Any] = []
        forecasts: list[Any] = []
        eda_outputs: list[Any] = []
        analysis_results: list[Any] = []

        for art in artifacts:
            kind = (art.kind or "").lower()
            content = art.content
            entry = {
                "id": art.id,
                "kind": art.kind,
                "title": art.title,
                "created_at": art.created_at,
                "content": content,
                "meta": art.meta,
                "message_id": art.message_id,
            }
            if kind == "chart":
                charts.append(content if content is not None else entry)
            elif kind == "forecast":
                forecasts.append(content if content is not None else entry)
            elif kind in {"eda", "profile"}:
                eda_outputs.append(content if content is not None else entry)
            elif kind in {"analysis_result", "insight", "hypothesis"}:
                analysis_results.append(content if content is not None else entry)

        chat_history = [
            {
                "id": m.id,
                "seq": m.seq,
                "role": m.role,
                "content": m.content or "",
                "created_at": m.created_at,
                "payload": m.payload,
            }
            for m in messages
        ]

        return sanitize_for_json(
            {
                "session_id": row.session_id,
                "title": row.title or "New analysis",
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "last_activity_at": row.last_activity_at,
                "dataset_id": row.dataset_id,
                "dataset_name": row.dataset_name or row.dataset_topic or "",
                "dataset_path": row.dataset_path or "",
                "dataset_url": row.dataset_url or "",
                "dataset_topic": row.dataset_topic or "",
                "current_dataset": row.current_dataset or {
                    "dataset_id": row.dataset_id,
                    "dataset_path": row.dataset_path,
                    "dataset_url": row.dataset_url,
                    "dataset_topic": row.dataset_topic,
                },
                "last_used_columns": list(
                    row.last_used_columns or row.last_columns or []
                ),
                "status": row.status or "active",
                "favorite": bool(row.favorite),
                "archived": bool(row.archived),
                "deleted": bool(row.deleted),
                "pinned": bool(getattr(row, "pinned", False)),
                "pin_order": getattr(row, "pin_order", None),
                "tags": list(row.tags_json or []),
                "message_count": int(row.message_count or 0),
                "chat_history": chat_history,
                "generated_charts": charts,
                "forecast_results": forecasts,
                "analysis_results": analysis_results,
                "eda_outputs": eda_outputs,
                "artifacts": [
                    {
                        "id": a.id,
                        "kind": a.kind,
                        "title": a.title,
                        "created_at": a.created_at,
                        "content": a.content,
                        "meta": a.meta,
                        "message_id": a.message_id,
                    }
                    for a in artifacts
                ],
                # Legacy fields
                "last_query": row.last_query or "",
                "last_insight": row.last_insight or "",
                "last_column": row.last_column or "",
                "last_columns": list(row.last_columns or []),
                "last_chart_type": row.last_chart_type or "",
                "last_intent": row.last_intent or "",
                "last_operation": row.last_operation or "",
                "last_forecast_target": row.last_forecast_target or "",
                "eda_summary": row.eda_summary or {},
            }
        )

    @staticmethod
    def _detach_copy(db: DbSession, row: AnalysisSession) -> AnalysisSession:
        """Return the row after expunging so callers can use attributes after close.

        We refresh key attributes into a simple namespace-like usage: keep bound
        until db closes by copying scalars only for ensure_session return.
        For ensure_session we only need the identity — return row while session
        is open is wrong after close. Copy essential fields onto a detached shell.
        """
        # Access attributes while bound
        _ = (
            row.session_id,
            row.dataset_path,
            row.dataset_url,
            row.dataset_topic,
            row.last_column,
            row.last_columns,
            row.last_chart_type,
            row.last_intent,
            row.last_operation,
            row.last_forecast_target,
            row.last_query,
            row.last_insight,
            row.eda_summary,
            row.title,
        )
        db.expunge(row)
        return row


_service: SessionService | None = None
_service_lock = threading.Lock()


def get_session_service() -> SessionService:
    global _service
    with _service_lock:
        if _service is None:
            _service = SessionService()
        return _service
