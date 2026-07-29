"""Session persistence service (Phase 1).

Responsibilities:
  - CRUD for AnalysisSession
  - Append chat messages
  - Store restorable artifacts (charts, forecasts, EDA, insights)
  - Dual-write to legacy session_memory for backward compatibility
  - Lazy-migrate legacy SessionMemory rows into AnalysisSession
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from backend.core.logger import get_logger
from backend.db import SessionLocal, SessionMemory, engine
from backend.sessions.models import AnalysisSession, SessionArtifact, SessionMessage
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_session_tables() -> None:
    """Create analysis_sessions / session_messages / session_artifacts if missing."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        # Import models so they register on Base.metadata
        from backend.sessions import models as _models  # noqa: F401

        AnalysisSession.__table__.create(bind=engine, checkfirst=True)
        SessionMessage.__table__.create(bind=engine, checkfirst=True)
        SessionArtifact.__table__.create(bind=engine, checkfirst=True)
        _schema_ready = True
        logger.info("Session persistence tables ready")


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session '{session_id}' not found")


class SessionService:
    """Production session store with legacy dual-write."""

    def __init__(self) -> None:
        ensure_session_tables()

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
                    return self._summary_dict(existing)

                # Idempotent create: return existing
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
                message_count=0,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
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
    ) -> dict[str, Any]:
        ensure_session_tables()
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))

        db = SessionLocal()
        try:
            # Ensure any legacy-only rows appear after migration on list
            self._migrate_all_legacy(db, user_id=user_id)

            q = db.query(AnalysisSession)
            if user_id:
                q = q.filter(AnalysisSession.user_id == user_id)
            if not include_deleted:
                q = q.filter(AnalysisSession.deleted.is_(False))
            if not include_archived:
                q = q.filter(AnalysisSession.archived.is_(False))

            total = q.count()
            rows = (
                q.order_by(AnalysisSession.updated_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "items": [self._summary_dict(r) for r in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
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
        status: str | None = None,
    ) -> dict[str, Any]:
        ensure_session_tables()
        db = SessionLocal()
        try:
            row = self._require_row(db, session_id)
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
            if status is not None:
                if status == "archived":
                    row.archived = True
                    row.status = "archived"
                elif status == "active":
                    row.archived = False
                    row.deleted = False
                    row.status = "active"
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            self._dual_write_legacy(db, row)
            return self._summary_dict(row)
        finally:
            db.close()

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
                return {"session_id": sid, "deleted": True, "hard": True}

            row.deleted = True
            row.status = "deleted"
            row.updated_at = _utcnow()
            db.commit()
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
                "dataset_id": row.dataset_id,
                "dataset_name": row.dataset_name,
                "dataset_topic": row.dataset_topic,
                "status": row.status or "active",
                "favorite": bool(row.favorite),
                "archived": bool(row.archived),
                "deleted": bool(row.deleted),
                "message_count": int(row.message_count or 0),
                "tags": list(row.tags_json or []),
                "last_query": row.last_query,
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
