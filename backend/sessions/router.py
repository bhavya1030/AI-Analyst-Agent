"""FastAPI routes for session management (Phase 1–8).

Static paths (/sessions/search, /sessions/recent, /sessions/import) are
registered before path parameters so they are not captured by /sessions/{id}.

Phase 8: every route resolves AuthUser via Depends and scopes queries by user_id.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse

from backend.auth.context import AuthUser
from backend.auth.deps import get_current_user
from backend.core.logger import get_logger
from backend.sessions.schemas import (
    SessionCreateRequest,
    SessionDuplicateRequest,
    SessionFavoriteRequest,
    SessionImportRequest,
    SessionPinRequest,
    SessionRenameRequest,
    SessionResumeRequest,
    SessionSwitchRequest,
    SessionUpdateRequest,
)
from backend.sessions.service import (
    SessionAccessDenied,
    SessionNotFoundError,
    get_session_service,
)
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


def _not_found(session_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": f"Session '{session_id}' not found",
            "code": "SESSION_NOT_FOUND",
        },
    )


def _forbidden(session_id: str, user_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": f"Access denied to session '{session_id}'",
            "code": "SESSION_ACCESS_DENIED",
            "user_id": user_id,
        },
    )


def _server_error(message: str, code: str, details: str | None = None) -> JSONResponse:
    body: dict = {"error": message, "code": code}
    if details:
        body["details"] = details
    return JSONResponse(status_code=500, content=body)


def _handle_access(exc: Exception, session_id: str, user_id: str | None):
    if isinstance(exc, SessionAccessDenied):
        return _forbidden(session_id, user_id)
    if isinstance(exc, SessionNotFoundError):
        return _not_found(session_id)
    return None


# ---------------------------------------------------------------------------
# Create / List
# ---------------------------------------------------------------------------


@router.post("/sessions", status_code=201)
@router.post("/v1/sessions", status_code=201)
def create_session(
    body: SessionCreateRequest | None = None,
    user: AuthUser = Depends(get_current_user),
):
    body = body or SessionCreateRequest()
    try:
        svc = get_session_service()
        created = svc.create_session(
            title=body.title,
            session_id=body.session_id,
            dataset_id=body.dataset_id,
            dataset_name=body.dataset_name,
            dataset_path=body.dataset_path,
            dataset_url=body.dataset_url,
            tags=body.tags,
            # Ownership from auth context — never trust body.user_id for isolation
            user_id=user.user_id,
        )
        return JSONResponse(status_code=201, content=sanitize_for_json(created))
    except SessionAccessDenied:
        return _forbidden(body.session_id or "", user.user_id)
    except Exception as exc:
        logger.error("Failed to create session", extra={"error": str(exc)})
        return _server_error("Unable to create session", "SESSION_CREATE_FAILED", str(exc))


@router.get("/sessions")
@router.get("/v1/sessions")
def list_sessions(
    detail: bool = Query(
        False,
        description="If false (default), return string[] of session ids for UI compatibility. "
        "If true, return paginated SessionListResponse.",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query(
        "updated_at",
        description="updated_at | created_at | last_activity_at | title | message_count | pin_order | status",
    ),
    order: str = Query("desc", description="asc | desc"),
    include_archived: bool = Query(True),
    include_deleted: bool = Query(False),
    status: Optional[str] = Query(None, description="active | archived | deleted"),
    favorite: Optional[bool] = Query(None),
    pinned: Optional[bool] = Query(None),
    archived: Optional[bool] = Query(None),
    tag: Optional[str] = Query(None),
    dataset_topic: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Free-text filter on title/query/topic"),
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        # Always filter by authenticated user (Phase 8)
        if not detail:
            return svc.list_session_ids(
                user_id=user.user_id, include_deleted=include_deleted
            )

        payload = svc.list_sessions(
            user_id=user.user_id,
            include_deleted=include_deleted,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            status=status,
            favorite=favorite,
            pinned=pinned,
            archived=archived,
            tag=tag,
            dataset_topic=dataset_topic,
            q=q,
        )
        return sanitize_for_json(payload)
    except Exception as exc:
        logger.error("Failed to list sessions", extra={"error": str(exc)})
        return _server_error("Unable to retrieve sessions", "SESSION_LIST_FAILED", str(exc))


# ---------------------------------------------------------------------------
# Static paths (must be before /sessions/{session_id})
# ---------------------------------------------------------------------------


@router.get("/sessions/search")
@router.get("/v1/sessions/search")
def search_sessions(
    q: str = Query(..., min_length=1, description="Full-text search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
    include_deleted: bool = Query(False),
    user: AuthUser = Depends(get_current_user),
):
    """Ranked full-text search — scoped to the calling user."""
    try:
        svc = get_session_service()
        payload = svc.search_sessions(
            q,
            user_id=user.user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
        return sanitize_for_json(payload)
    except Exception as exc:
        logger.error("Session search failed", extra={"error": str(exc), "q": q})
        return _server_error("Unable to search sessions", "SESSION_SEARCH_FAILED", str(exc))


@router.get("/sessions/recent")
@router.get("/v1/sessions/recent")
def recent_sessions(
    limit: int = Query(10, ge=1, le=100),
    include_archived: bool = Query(False),
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        payload = svc.recent_sessions(
            user_id=user.user_id,
            limit=limit,
            include_archived=include_archived,
        )
        return sanitize_for_json(payload)
    except Exception as exc:
        logger.error("Failed to load recent sessions", extra={"error": str(exc)})
        return _server_error(
            "Unable to retrieve recent sessions", "SESSION_RECENT_FAILED", str(exc)
        )


@router.post("/sessions/switch")
@router.post("/v1/sessions/switch")
def switch_session(
    body: SessionSwitchRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Flush optional from-session continuity and restore to-session checkpoint."""
    try:
        svc = get_session_service()
        # Ownership of both ends
        if body.from_session_id:
            svc.assert_session_owner(body.from_session_id, user.user_id)
        svc.assert_session_owner(body.to_session_id, user.user_id)

        from backend.graph.checkpoint_service import get_checkpoint_service

        result = get_checkpoint_service().switch_session(
            body.from_session_id,
            body.to_session_id,
        )
        payload = {
            "from_session_id": result.get("from_session_id"),
            "to_session_id": result.get("to_session_id"),
            "switched": True,
            "resumable": bool(result.get("resumable")),
            "message": result.get("message"),
            "checkpoint": result.get("checkpoint"),
            "planner_state": result.get("planner_state") or {},
            "dataset_ref": result.get("dataset_ref") or {},
            "graph_resumable": bool(result.get("resumable")),
            "user_id": user.user_id,
        }
        return sanitize_for_json(payload)
    except SessionAccessDenied:
        return _forbidden(body.to_session_id, user.user_id)
    except SessionNotFoundError as exc:
        return _not_found(exc.session_id)
    except Exception as exc:
        logger.error("Session switch failed", extra={"error": str(exc)})
        return _server_error("Unable to switch session", "SESSION_SWITCH_FAILED", str(exc))


@router.post("/sessions/import", status_code=201)
@router.post("/v1/sessions/import", status_code=201)
def import_session(
    body: SessionImportRequest,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        result = svc.import_session(
            body.bundle,
            session_id=body.session_id,
            title=body.title,
            user_id=user.user_id,
        )
        return JSONResponse(status_code=201, content=sanitize_for_json(result))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "code": "SESSION_IMPORT_INVALID"},
        )
    except Exception as exc:
        logger.error("Failed to import session", extra={"error": str(exc)})
        return _server_error("Unable to import session", "SESSION_IMPORT_FAILED", str(exc))


@router.get("/auth/me")
@router.get("/v1/auth/me")
def auth_me(user: AuthUser = Depends(get_current_user)):
    """Return resolved identity for debugging / future JWT clients."""
    return sanitize_for_json(user.to_dict())


# ---------------------------------------------------------------------------
# Single session CRUD
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}")
@router.get("/v1/sessions/{session_id}")
def get_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        detail = svc.get_session_detail(session_id, user_id=user.user_id)
        return sanitize_for_json(detail)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to load session detail",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to retrieve session", "SESSION_GET_FAILED", str(exc))


@router.put("/sessions/{session_id}")
@router.put("/v1/sessions/{session_id}")
def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        updated = svc.update_session(
            session_id,
            user_id=user.user_id,
            title=body.title,
            dataset_id=body.dataset_id,
            dataset_name=body.dataset_name,
            dataset_path=body.dataset_path,
            dataset_url=body.dataset_url,
            dataset_topic=body.dataset_topic,
            tags=body.tags,
            favorite=body.favorite,
            pinned=body.pinned,
            status=body.status,
        )
        return sanitize_for_json(updated)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to update session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to update session", "SESSION_UPDATE_FAILED", str(exc))


@router.delete("/sessions/{session_id}")
@router.delete("/v1/sessions/{session_id}")
def delete_session(
    session_id: str,
    hard: bool = Query(False, description="Permanently delete when true; soft-delete by default."),
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        result = svc.delete_session(session_id, user_id=user.user_id, hard=hard)
        return sanitize_for_json(result)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to delete session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to delete session", "SESSION_DELETE_FAILED", str(exc))


# ---------------------------------------------------------------------------
# Phase 3 actions
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/rename")
@router.post("/v1/sessions/{session_id}/rename")
def rename_session(
    session_id: str,
    body: SessionRenameRequest,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        result = svc.rename_session(session_id, body.title, user_id=user.user_id)
        return sanitize_for_json(result)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "code": "SESSION_RENAME_INVALID"},
        )
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to rename session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to rename session", "SESSION_RENAME_FAILED", str(exc))


@router.post("/sessions/{session_id}/archive")
@router.post("/v1/sessions/{session_id}/archive")
def archive_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        result = svc.archive_session(session_id, user_id=user.user_id)
        return sanitize_for_json(result)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to archive session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to archive session", "SESSION_ARCHIVE_FAILED", str(exc))


@router.post("/sessions/{session_id}/restore")
@router.post("/v1/sessions/{session_id}/restore")
def restore_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        result = svc.restore_session(session_id, user_id=user.user_id)
        return sanitize_for_json(result)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to restore session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to restore session", "SESSION_RESTORE_FAILED", str(exc))


@router.post("/sessions/{session_id}/favorite")
@router.post("/v1/sessions/{session_id}/favorite")
def favorite_session(
    session_id: str,
    body: SessionFavoriteRequest | None = Body(default=None),
    user: AuthUser = Depends(get_current_user),
):
    body = body or SessionFavoriteRequest()
    try:
        svc = get_session_service()
        result = svc.set_favorite(session_id, body.favorite, user_id=user.user_id)
        return sanitize_for_json(result)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to favorite session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error(
            "Unable to update favorite", "SESSION_FAVORITE_FAILED", str(exc)
        )


@router.post("/sessions/{session_id}/pin")
@router.post("/v1/sessions/{session_id}/pin")
def pin_session(
    session_id: str,
    body: SessionPinRequest | None = Body(default=None),
    user: AuthUser = Depends(get_current_user),
):
    body = body or SessionPinRequest()
    try:
        svc = get_session_service()
        result = svc.set_pinned(
            session_id,
            body.pinned,
            pin_order=body.pin_order,
            user_id=user.user_id,
        )
        return sanitize_for_json(result)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to pin session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to pin session", "SESSION_PIN_FAILED", str(exc))


@router.post("/sessions/{session_id}/duplicate", status_code=201)
@router.post("/v1/sessions/{session_id}/duplicate", status_code=201)
def duplicate_session(
    session_id: str,
    body: SessionDuplicateRequest | None = Body(default=None),
    user: AuthUser = Depends(get_current_user),
):
    body = body or SessionDuplicateRequest()
    try:
        svc = get_session_service()
        result = svc.duplicate_session(
            session_id,
            user_id=user.user_id,
            title=body.title,
            include_messages=body.include_messages,
            include_artifacts=body.include_artifacts,
        )
        return JSONResponse(status_code=201, content=sanitize_for_json(result))
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to duplicate session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error(
            "Unable to duplicate session", "SESSION_DUPLICATE_FAILED", str(exc)
        )


@router.get("/sessions/{session_id}/export")
@router.get("/v1/sessions/{session_id}/export")
def export_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        svc = get_session_service()
        bundle = svc.export_session(session_id, user_id=user.user_id)
        return sanitize_for_json(bundle)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to export session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error("Unable to export session", "SESSION_EXPORT_FAILED", str(exc))


# ---------------------------------------------------------------------------
# Phase 6 — Checkpoints / resume / crash recovery
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/checkpoints")
@router.get("/v1/sessions/{session_id}/checkpoints")
def list_session_checkpoints(
    session_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
):
    try:
        get_session_service().assert_session_owner(session_id, user.user_id)
        from backend.graph.checkpoint_service import get_checkpoint_service

        payload = get_checkpoint_service().list_session_checkpoints(
            session_id, limit=limit
        )
        return sanitize_for_json(payload)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to list checkpoints",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error(
            "Unable to list checkpoints", "SESSION_CHECKPOINTS_FAILED", str(exc)
        )


@router.post("/sessions/{session_id}/resume")
@router.post("/v1/sessions/{session_id}/resume")
def resume_session(
    session_id: str,
    body: SessionResumeRequest | None = Body(default=None),
    user: AuthUser = Depends(get_current_user),
):
    body = body or SessionResumeRequest()
    try:
        get_session_service().assert_session_owner(session_id, user.user_id)
        from backend.graph.checkpoint_service import get_checkpoint_service

        result = get_checkpoint_service().resume_session(
            session_id, question=body.question
        )
        gs = result.get("graph_state") or {}
        safe_preview = {
            k: v
            for k, v in gs.items()
            if k not in {"data", "last_dataset"}
            and type(v).__name__ not in {"DataFrame", "Series"}
        }
        payload = {
            "session_id": session_id,
            "resumable": bool(result.get("resumable")),
            "message": result.get("message") or "",
            "checkpoint": result.get("checkpoint"),
            "planner_state": result.get("planner_state") or {},
            "dataset_ref": result.get("dataset_ref") or {},
            "graph_resumable": bool(result.get("resumable")),
            "graph_state_preview": sanitize_for_json(safe_preview),
            "user_id": user.user_id,
        }
        return sanitize_for_json(payload)
    except SessionAccessDenied:
        return _forbidden(session_id, user.user_id)
    except SessionNotFoundError:
        return _not_found(session_id)
    except Exception as exc:
        logger.error(
            "Failed to resume session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return _server_error(
            "Unable to resume session", "SESSION_RESUME_FAILED", str(exc)
        )
