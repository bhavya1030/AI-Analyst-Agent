"""FastAPI routes for session CRUD (Phase 1)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.core.logger import get_logger
from backend.sessions.schemas import SessionCreateRequest, SessionUpdateRequest
from backend.sessions.service import SessionNotFoundError, get_session_service
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


@router.post("/sessions")
@router.post("/v1/sessions")
def create_session(body: SessionCreateRequest | None = None):
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
            user_id=body.user_id or "anonymous",
        )
        return JSONResponse(status_code=201, content=sanitize_for_json(created))
    except Exception as exc:
        logger.error("Failed to create session", extra={"error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to create session", "details": str(exc), "code": "SESSION_CREATE_FAILED"},
        )


@router.get("/sessions")
@router.get("/v1/sessions")
def list_sessions(
    detail: bool = Query(
        False,
        description="If false (default), return string[] of session ids for UI compatibility. "
        "If true, return {items,total,limit,offset} summaries.",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(True),
    include_deleted: bool = Query(False),
    user_id: Optional[str] = Query(None),
):
    try:
        svc = get_session_service()
        if not detail:
            # Backward compatible with analytics-copilot-ui fetchSessions()
            return svc.list_session_ids(include_deleted=include_deleted)

        payload = svc.list_sessions(
            user_id=user_id,
            include_deleted=include_deleted,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return sanitize_for_json(payload)
    except Exception as exc:
        logger.error("Failed to list sessions", extra={"error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to retrieve sessions", "code": "SESSION_LIST_FAILED"},
        )


@router.get("/sessions/{session_id}")
@router.get("/v1/sessions/{session_id}")
def get_session(session_id: str):
    try:
        svc = get_session_service()
        detail = svc.get_session_detail(session_id)
        return sanitize_for_json(detail)
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Session '{session_id}' not found",
                "code": "SESSION_NOT_FOUND",
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to load session detail",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to retrieve session", "code": "SESSION_GET_FAILED"},
        )


@router.put("/sessions/{session_id}")
@router.put("/v1/sessions/{session_id}")
def update_session(session_id: str, body: SessionUpdateRequest):
    try:
        svc = get_session_service()
        updated = svc.update_session(
            session_id,
            title=body.title,
            dataset_id=body.dataset_id,
            dataset_name=body.dataset_name,
            dataset_path=body.dataset_path,
            dataset_url=body.dataset_url,
            dataset_topic=body.dataset_topic,
            tags=body.tags,
            favorite=body.favorite,
            status=body.status,
        )
        return sanitize_for_json(updated)
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Session '{session_id}' not found",
                "code": "SESSION_NOT_FOUND",
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to update session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to update session", "details": str(exc), "code": "SESSION_UPDATE_FAILED"},
        )


@router.delete("/sessions/{session_id}")
@router.delete("/v1/sessions/{session_id}")
def delete_session(
    session_id: str,
    hard: bool = Query(False, description="Permanently delete when true; soft-delete by default."),
):
    try:
        svc = get_session_service()
        result = svc.delete_session(session_id, hard=hard)
        return sanitize_for_json(result)
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Session '{session_id}' not found",
                "code": "SESSION_NOT_FOUND",
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to delete session",
            extra={"session_id": session_id, "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to delete session", "details": str(exc), "code": "SESSION_DELETE_FAILED"},
        )
